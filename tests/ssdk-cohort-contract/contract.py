"""Sequential specification, NOT an installed SDK coordinator or reader lock."""
from dataclasses import dataclass, field
from typing import Optional

MAX = (1 << 64) - 1
FIELDS = {
    "mdio_set": "write16", "mdio_get": "read16",
    "i2c_set": "write16", "i2c_get": "read16",
    "header_reg_set": "bytes", "header_reg_get": "bytes",
    "psgmii_reg_set": "bytes", "psgmii_reg_get": "bytes",
    "uniphy_reg_set": "indexed_bytes", "uniphy_reg_get": "indexed_bytes",
    "mii_reg_set": "write32", "mii_reg_get": "read32",
}
STAGES = ("platform", "hsl", "vlan", "adapter", "phy", "sfp", "producers")
KINDS = ("uk", "fal", "sd", "direct", "phy")


class Rejected(Exception):
    pass


def need(ok, reason):
    if not ok:
        raise Rejected(reason)


@dataclass(frozen=True)
class Callback:
    signature: str
    identity: str


@dataclass(frozen=True)
class Owner:
    epoch: int
    device: int
    serial: int


@dataclass(frozen=True)
class Operation:
    owner: Owner
    serial: int
    role: str


@dataclass(frozen=True)
class Reader:
    owner: Owner
    serial: int
    kind: str
    internal: bool
    field: Optional[str] = None
    callback: Optional[Callback] = None


@dataclass
class Cell:
    owner: Owner
    selected: frozenset
    status: dict = field(default_factory=dict)
    prefix: bool = False
    contexts: set = field(default_factory=set)
    first_error: Optional[str] = None
    phy_type: str = "common"


class Cohort:
    """Opaque tokens represent trusted bookkeeping, not security capabilities.

    Each method is an atomic model step. Real gate synchronization, memory
    ordering, producer drains and callback ownership certificates are NOT
    supplied by this class. A future SDK implementation must supply them.
    """

    def __init__(self, baseline=None, capacity=3, foreign_uk=False, borrowed_phy_types=()):
        need(capacity > 0, "capacity")
        self.capacity = capacity
        self.baseline = {name: None for name in FIELDS}
        self.baseline.update(baseline or {})
        self._typed(self.baseline)
        self.foreign_uk = foreign_uk
        self.epoch = self.serial = self.read_serial = self.op_serial = 0
        self.phase = "OFF"
        self.cells = {}
        self.readers = {}
        self.operation = None
        self.staged = dict(self.baseline)
        self.publication = dict(self.baseline)
        self.registered = self.published = False
        self.uk_retire_count = self.restore_count = self.unmap_count = 0
        self.first_error = None
        self.prefix_uncertain = False
        self.phy_holders = {}
        self.phy_owned = set()
        self.borrowed_phy_types = frozenset(borrowed_phy_types)
        self.phy_frees = []
        self.native_mutex_initializations = 1

    @staticmethod
    def _typed(vector):
        need(set(vector) <= set(FIELDS), "callback-field")
        for name, callback in vector.items():
            need(callback is None or (isinstance(callback, Callback) and
                 callback.signature == FIELDS[name]), "callback-type")

    def _cell(self, owner):
        need(isinstance(owner, Owner) and owner.epoch == self.epoch, "owner-epoch")
        cell = self.cells.get(owner.device)
        need(cell is not None and cell.owner == owner, "owner-identity")
        return cell

    def _op(self, operation):
        need(operation is not None and operation == self.operation, "operation-identity")
        return self._cell(operation.owner)

    def _readers(self, device=None):
        return [r for r in self.readers.values()
                if device is None or r.owner.device == device]

    def _error(self, cell, error):
        if cell.first_error is None:
            cell.first_error = error
        if self.first_error is None:
            self.first_error = error

    def start(self):
        need(self.phase == "OFF" and not self.cells and not self.readers and
             self.operation is None and not self.registered, "root-still-held")
        need(self.epoch < MAX, "epoch-exhausted")
        need(self.publication == self.baseline and not self.published, "publication-replaced")
        self.epoch += 1
        self.phase = "BUILD"
        self.staged = dict(self.baseline)
        self.first_error = None
        self.prefix_uncertain = False
        return self.epoch

    def reserve(self, device, selected=("hsl", "vlan", "adapter", "phy", "producers"), phy_type="common"):
        need(self.phase == "BUILD" and self.operation is None, "reserve-phase")
        need(type(device) is int and 0 <= device < self.capacity, "device")
        need(device not in self.cells, "occupied")
        selected = frozenset(selected)
        need("hsl" in selected and selected <= set(STAGES) - {"platform"}, "selected-stage")
        need(isinstance(phy_type, str) and phy_type, "phy-type")
        need(self.serial < MAX, "owner-exhausted")
        self.serial += 1
        owner = Owner(self.epoch, device, self.serial)
        self.cells[device] = Cell(owner, selected, phy_type=phy_type)
        return owner

    def begin(self, owner, role):
        self._cell(owner)
        need(self.operation is None, "writer-busy")
        need((role == "construct" and self.phase == "BUILD") or
             (role == "retire" and self.phase in ("STOPPING", "PREFIX_RETIRED")),
             "operation-phase")
        need(self.op_serial < MAX, "operation-exhausted")
        self.op_serial += 1
        self.operation = Operation(owner, self.op_serial, role)
        return self.operation

    def end(self, operation):
        self._op(operation)
        need(not any(r.internal for r in self.readers.values()), "internal-readers")
        self.operation = None

    def record(self, operation, stage, outcome="owned"):
        cell = self._op(operation)
        need(operation.role == "construct" and stage in STAGES, "record-role")
        need(stage not in cell.status, "already-recorded")
        need(outcome in ("owned", "borrowed", "skip", "failed-clean", "failed-held", "unknown"),
             "outcome")
        if stage != "platform":
            need(cell.prefix and cell.status.get("platform") in ("owned", "borrowed"), "no-prefix")
            need(stage in cell.selected or outcome == "skip", "unselected-stage")
        dependencies = {"vlan": ("hsl",), "adapter": ("hsl", "vlan"),
                        "phy": ("hsl", "vlan", "adapter"), "sfp": ("hsl", "phy"),
                        "producers": ("hsl", "vlan", "adapter", "phy")}
        for dependency in dependencies.get(stage, ()):
            if dependency in cell.selected:
                need(cell.status.get(dependency) in ("owned", "borrowed"), "constructor-dependency")
        if stage == "phy" and outcome in ("owned", "borrowed"):
            need(cell.owner in self.phy_holders.get(cell.phy_type, set()), "phy-lease-proof")
        if outcome == "skip":
            need(stage not in cell.selected and stage != "platform", "unproved-skip")
        cell.status[stage] = outcome
        if outcome.startswith("failed") or outcome == "unknown":
            self._error(cell, stage + ":" + outcome)

    def prefix(self, operation, requested, uk_result="ok"):
        cell = self._op(operation)
        need(operation.role == "construct" and not cell.prefix, "prefix-role")
        need(cell.status.get("platform") in ("owned", "borrowed"), "no-platform")
        need(not self.foreign_uk, "foreign-uk")
        need(not self.readers, "reader-busy")
        self._typed(requested)
        candidate = dict(self.staged)
        for name, callback in requested.items():
            if callback is not None:
                need(candidate[name] in (None, callback), "callback-conflict")
                candidate[name] = callback
        need(uk_result in ("ok", "failed-clean", "unknown"), "uk-outcome")
        if uk_result != "ok":
            self._error(cell, "uk:" + uk_result)
            if uk_result == "unknown":
                cell.status["uk-unknown"] = "unknown"
            return False
        self.staged = candidate
        self.registered = True  # Private/paused, NOT public root readiness.
        cell.prefix = True
        return True

    def certify_context(self, operation, fields):
        cell = self._op(operation)
        need(operation.role == "construct" and cell.prefix, "context-role")
        need(set(fields) <= set(FIELDS), "context-field")
        cell.contexts.update(fields)

    def claim_phy_ref(self, operation, ownership):
        cell = self._op(operation)
        need(operation.role == "construct" and cell.prefix, "phy-ref-role")
        owners = self.phy_holders.get(cell.phy_type, set())
        need(cell.owner not in owners, "phy-ref-duplicate")
        if ownership == "new":
            need(cell.phy_type not in self.phy_holders and
                 cell.phy_type not in self.borrowed_phy_types, "phy-ref-not-new")
        else:
            need(ownership == "borrowed" and (cell.phy_type in self.phy_holders or
                 cell.phy_type in self.borrowed_phy_types), "phy-ref-not-borrowed")
        self.phy_holders.setdefault(cell.phy_type, set()).add(cell.owner)
        if ownership == "new":
            self.phy_owned.add(cell.phy_type)

    def commit(self):
        need(self.phase == "BUILD" and self.operation is None and not self.readers, "commit-phase")
        need(self.cells and all(c.prefix and c.first_error is None and
             all(c.status.get(s) in ("owned", "borrowed") for s in c.selected) and
             c.status.get("platform") in ("owned", "borrowed") for c in self.cells.values()),
             "not-root-ready")
        need(self.publication == self.baseline, "publication-replaced")
        self.publication = dict(self.staged)
        self.published = True
        self.phase = "LIVE"

    def get(self, device, kind, field=None, operation=None):
        need(kind in KINDS, "reader-kind")
        cell = self.cells.get(device)
        need(cell is not None and cell.prefix, "no-reader-owner")
        internal = operation is not None
        if internal:
            need(self._op(operation) is cell, "internal-device")
        else:
            need(self.phase == "LIVE" and self.published and self.operation is None, "admission-closed")
        need(cell.status.get("platform") in ("owned", "borrowed"), "provider-gone")
        if kind in ("fal", "uk"):
            need(cell.status.get("hsl") in ("owned", "borrowed"), "hsl-not-ready")
        if kind == "phy":
            need(cell.status.get("phy") in ("owned", "borrowed") and
                 cell.owner in self.phy_holders.get(cell.phy_type, set()), "phy-not-held")
        callback = None
        if kind == "sd":
            need(internal or self.publication == self.staged, "publication-replaced")
            view = self.staged if internal else self.publication
            need(field in FIELDS and view[field] is not None and field in cell.contexts,
                 "provider-not-ready")
            callback = view[field]
        else:
            need(field is None, "unexpected-reader-field")
        need(self.read_serial < MAX, "reader-exhausted")
        self.read_serial += 1
        reader = Reader(cell.owner, self.read_serial, kind, internal, field, callback)
        self.readers[reader.serial] = reader
        return reader

    def put(self, reader):
        need(isinstance(reader, Reader) and self.readers.get(reader.serial) == reader, "reader-identity")
        del self.readers[reader.serial]

    def close_admission(self):
        need(self.phase in ("BUILD", "LIVE", "STOPPING") and self.operation is None,
             "close-phase")
        self.phase = "STOPPING"
        return not self.readers  # False is pending, not a retirement certificate.

    def retire(self, operation, stage, outcome="ok"):
        cell = self._op(operation)
        need(operation.role == "retire", "retire-role")
        need(not self._readers(cell.owner.device), "reader-busy")
        status = cell.status.get(stage)
        need(status in ("owned", "borrowed", "failed-held"), "not-retire-owned")
        if stage == "platform":
            need(self.phase == "PREFIX_RETIRED" and not cell.prefix and
                 not any(s != "platform" and v not in ("skip", "failed-clean")
                         for s, v in cell.status.items()), "platform-too-early")
        else:
            need(self.phase == "STOPPING", "retire-phase")
            need(stage == "producers" or cell.status.get("producers") not in
                 ("owned", "borrowed", "failed-held", "unknown"), "producer-live")
            need(stage not in ("hsl", "phy") or cell.status.get("sfp") not in
                 ("owned", "borrowed", "failed-held", "unknown"), "sfp-needs-port")
        need(outcome in ("ok", "failed", "unknown"), "retire-outcome")
        if outcome != "ok":
            self._error(cell, stage + ":retire-" + outcome)
            if outcome == "unknown":
                cell.status[stage] = "unknown"
            return False
        del cell.status[stage]
        if stage == "platform" and status != "borrowed":
            self.unmap_count += 1
        return True

    def drop_phy_ref(self, operation):
        cell = self._op(operation)
        need(operation.role == "retire" and self.phase == "STOPPING", "phy-drop-role")
        need(not self._readers(cell.owner.device) and
             cell.status.get("phy") in (None, "skip", "failed-clean") and
             cell.status.get("producers") in (None, "skip", "failed-clean") and
             cell.status.get("sfp") in (None, "skip", "failed-clean"), "phy-drop-pending")
        owners = self.phy_holders.get(cell.phy_type, set())
        need(cell.owner in owners, "phy-ref-unowned")
        owners.remove(cell.owner)

    def drop_consumer(self, operation):
        cell = self._op(operation)
        need(operation.role == "retire" and self.phase == "STOPPING" and cell.prefix,
             "drop-role")
        need(not self._readers(cell.owner.device) and
             all(s == "platform" or v in ("skip", "failed-clean") for s, v in cell.status.items()),
             "consumer-stage-pending")
        need(not any(cell.owner in owners for owners in self.phy_holders.values()), "phy-ref-held")
        cell.prefix = False

    def finish_prefix(self, uk_result="ok"):
        need(self.phase == "STOPPING" and self.operation is None, "finish-phase")
        need(not self.prefix_uncertain, "prefix-unknown")
        need(not self.readers and not any(c.prefix for c in self.cells.values()), "not-last-quiescent")
        need(all(all(s == "platform" or v in ("skip", "failed-clean") for s, v in c.status.items())
                 for c in self.cells.values()), "residual-stage")
        need(self.publication == (self.staged if self.published else self.baseline),
             "publication-replaced")
        need(uk_result in ("ok", "busy", "unknown"), "uk-retire-outcome")
        need(not any(self.phy_holders.values()), "phy-shared-held")
        if uk_result != "ok":
            if uk_result == "unknown":
                self.prefix_uncertain = True
                if self.first_error is None:
                    self.first_error = "uk:retire-unknown"
            return False  # Keep endpoint/publication AND provider ownership.
        if self.registered:
            self.uk_retire_count += 1
        if self.published:
            self.restore_count += 1
        self.registered = self.published = False
        self.publication = dict(self.baseline)
        self.phy_frees.extend(sorted(self.phy_owned))
        self.phy_owned.clear()
        self.phy_holders.clear()
        self.phase = "PREFIX_RETIRED"
        return True

    def release_cell(self, operation):
        cell = self._op(operation)
        need(self.phase == "PREFIX_RETIRED" and not cell.prefix and
             all(v in ("skip", "failed-clean") for v in cell.status.values()), "cell-held")
        owner = cell.owner
        self.end(operation)
        del self.cells[owner.device]

    def module_exit_ready(self):
        return self.phase == "OFF" and not self.cells and not self.readers and not self.registered

    def finish_root(self):
        need(self.phase == "PREFIX_RETIRED" and not self.cells and not self.readers and
             self.operation is None, "root-held")
        self.phase = "OFF"
