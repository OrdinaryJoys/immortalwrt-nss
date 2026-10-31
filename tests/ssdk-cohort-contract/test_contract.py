"""Executable design obligations, not production-C or kernel validation."""
import copy
from dataclasses import replace
import io
import itertools
import json
import re
import sys
import unittest

sys.dont_write_bytecode = True
from contract import Callback, Cohort, FIELDS, KINDS, MAX, Rejected

CALLBACK = Callback("bytes", "qca_header")
SELECTED = ("hsl", "vlan", "adapter", "phy", "producers")


def prepare(count=1, cohort=None, selected=SELECTED, requested=None):
    c = cohort or Cohort()
    c.start()
    owners = []
    for device in range(count):
        owner = c.reserve(device, selected)
        owners.append(owner)
        op = c.begin(owner, "construct")
        c.record(op, "platform")
        c.prefix(op, requested or {})
        c.certify_context(op, [f for f, cb in c.staged.items() if cb is not None])
        for stage in ("hsl", "vlan", "adapter", "phy", "sfp", "producers"):
            if stage in selected:
                if stage == "phy":
                    mode = "borrowed" if "common" in c.phy_holders or "common" in c.borrowed_phy_types else "new"
                    c.claim_phy_ref(op, mode)
                c.record(op, stage)
        c.end(op)
    return c, owners


def retire_consumer(c, owner):
    op = c.begin(owner, "retire")
    cell = c.cells[owner.device]
    for stage in ("producers", "sfp", "adapter", "hsl", "vlan", "phy"):
        if cell.status.get(stage) in ("owned", "borrowed", "failed-held"):
            c.retire(op, stage)
    if owner in c.phy_holders.get(cell.phy_type, set()):
        c.drop_phy_ref(op)
    if cell.prefix:
        c.drop_consumer(op)
    c.end(op)


def finish(c, owners):
    c.finish_prefix()
    for owner in owners:
        op = c.begin(owner, "retire")
        if "platform" in c.cells[owner.device].status:
            c.retire(op, "platform")
        c.release_cell(op)
    c.finish_root()


class Contracts(unittest.TestCase):
    def reject(self, c, reason, call):
        before = copy.deepcopy(c.__dict__)
        with self.assertRaisesRegex(Rejected, "^" + re.escape(reason) + "$"):
            call()
        self.assertEqual(c.__dict__, before, "rejection changed owned state")

    def test_private_public_readiness(self):
        c, owners = prepare()
        self.assertTrue(c.registered)
        self.assertFalse(c.published)
        self.reject(c, "admission-closed", lambda: c.get(0, "uk"))
        c.commit()
        r = c.get(0, "uk")
        c.put(r)

    def test_optional_union_null_inheritance(self):
        c, owners = prepare(1, requested={"header_reg_get": CALLBACK})
        other = c.reserve(1)
        op = c.begin(other, "construct")
        c.record(op, "platform")
        c.prefix(op, {"header_reg_get": None, "uniphy_reg_get": Callback("indexed_bytes", "uniphy")})
        self.assertEqual(c.staged["header_reg_get"], CALLBACK)
        self.assertEqual(c.publication, c.baseline)
        self.assertFalse(c.published)

    def test_conflict_and_type_are_preflight(self):
        c, owners = prepare(1, requested={"header_reg_get": CALLBACK})
        other = c.reserve(1)
        op = c.begin(other, "construct")
        c.record(op, "platform")
        self.reject(c, "callback-conflict", lambda: c.prefix(op, {"header_reg_get": Callback("bytes", "foreign")}))
        self.reject(c, "callback-type", lambda: c.prefix(op, {"header_reg_get": Callback("read32", "wrong")}))

    def test_foreign_uk_not_adopted(self):
        c = Cohort(foreign_uk=True)
        c.start()
        owner = c.reserve(0)
        op = c.begin(owner, "construct")
        c.record(op, "platform")
        self.reject(c, "foreign-uk", lambda: c.prefix(op, {}))

    def test_failed_prefix_keeps_peer_private_state(self):
        c, owners = prepare(1, requested={"header_reg_get": CALLBACK})
        other = c.reserve(1)
        op = c.begin(other, "construct")
        c.record(op, "platform")
        old = dict(c.staged)
        self.assertFalse(c.prefix(op, {"psgmii_reg_get": CALLBACK}, "failed-clean"))
        self.assertEqual(c.staged, old)
        self.assertFalse(c.cells[1].prefix)
        self.assertTrue(c.cells[0].prefix)
        c.end(op)
        self.reject(c, "not-root-ready", c.commit)
        c.close_admission()
        retire_consumer(c, owners[0])
        finish(c, [*owners, other])
        self.assertEqual(c.uk_retire_count, 1)

    def test_reservation_is_not_acquisition(self):
        c = Cohort()
        c.start()
        owner = c.reserve(0)
        c.close_admission()
        op = c.begin(owner, "retire")
        self.reject(c, "drop-role", lambda: c.drop_consumer(op))
        self.reject(c, "not-retire-owned", lambda: c.retire(op, "platform"))
        c.end(op)
        finish(c, [owner])
        self.assertEqual(c.uk_retire_count, 0)

    def test_all_reader_classes_block_teardown(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                c, owners = prepare(requested={"header_reg_get": CALLBACK})
                c.commit()
                reader = c.get(0, kind, "header_reg_get" if kind == "sd" else None)
                self.assertFalse(c.close_admission())
                self.reject(c, "admission-closed", lambda: c.get(0, kind))
                op = c.begin(owners[0], "retire")
                self.reject(c, "reader-busy", lambda: c.retire(op, "producers"))
                c.end(op)
                c.put(reader)
                retire_consumer(c, owners[0])
                finish(c, owners)

    def test_explicit_internal_continuation(self):
        c, owners = prepare(2, requested={"header_reg_get": CALLBACK})
        op = c.begin(owners[0], "construct")
        reader = c.get(0, "sd", "header_reg_get", op)
        self.reject(c, "internal-device", lambda: c.get(1, "sd", "header_reg_get", op))
        self.reject(c, "internal-readers", lambda: c.end(op))
        self.reject(c, "writer-busy", lambda: c.begin(owners[1], "construct"))
        c.put(reader)
        c.end(op)
        self.reject(c, "operation-identity", lambda: c.record(op, "sfp"))

    def test_provider_context_not_callback_presence(self):
        c, owners = prepare(requested={"header_reg_get": CALLBACK})
        c.cells[0].contexts.clear()  # Deliberately absent provider certificate.
        c.commit()
        self.reject(c, "provider-not-ready", lambda: c.get(0, "sd", "header_reg_get"))

    def test_last_holder_all_three_orders(self):
        for order in itertools.permutations(range(3)):
            c, owners = prepare(3)
            c.commit()
            c.close_admission()
            for i in order:
                retire_consumer(c, owners[i])
                if any(x.prefix for x in c.cells.values()):
                    self.reject(c, "not-last-quiescent", c.finish_prefix)
                self.assertEqual(c.uk_retire_count, 0)
                self.assertEqual(c.unmap_count, 0)
                self.assertEqual(c.phy_frees, [])
            finish(c, owners)
            self.assertEqual(c.uk_retire_count, 1)
            self.assertEqual(c.phy_frees, ["common"])
            self.assertEqual(c.unmap_count, 3)

    def test_hsl_done_does_not_drop_late_stages(self):
        c, owners = prepare()
        c.commit()
        c.close_admission()
        op = c.begin(owners[0], "retire")
        c.retire(op, "producers")
        c.retire(op, "adapter")
        c.retire(op, "hsl")
        self.reject(c, "consumer-stage-pending", lambda: c.drop_consumer(op))
        c.retire(op, "vlan")
        self.reject(c, "consumer-stage-pending", lambda: c.drop_consumer(op))
        c.retire(op, "phy")
        self.reject(c, "phy-ref-held", lambda: c.drop_consumer(op))
        c.drop_phy_ref(op)
        c.drop_consumer(op)
        c.end(op)
        finish(c, owners)

    def test_producer_and_sfp_order(self):
        c, owners = prepare(selected=(*SELECTED, "sfp"))
        c.commit()
        c.close_admission()
        op = c.begin(owners[0], "retire")
        self.reject(c, "producer-live", lambda: c.retire(op, "hsl"))
        c.retire(op, "producers")
        self.reject(c, "sfp-needs-port", lambda: c.retire(op, "hsl"))

    def test_sfp_before_phy_for_all_unresolved_states(self):
        for state in ("owned", "borrowed", "failed-held", "unknown"):
            with self.subTest(state=state):
                c, owners = prepare(2, selected=(*SELECTED, "sfp"))
                c.commit()
                c.close_admission()
                c.cells[0].status["sfp"] = state  # Destructor/borrow oracle.
                op = c.begin(owners[0], "retire")
                c.retire(op, "producers")
                self.reject(c, "sfp-needs-port", lambda: c.retire(op, "phy"))
                self.reject(c, "phy-drop-pending", lambda: c.drop_phy_ref(op))
                if state != "unknown":
                    c.retire(op, "sfp")
                    c.retire(op, "phy")
                    c.drop_phy_ref(op)
                    self.assertEqual(c.phy_holders["common"], {owners[1]})
                    self.assertEqual(c.phy_frees, [])

    def test_failure_retains_owner_and_first_error(self):
        c, owners = prepare()
        c.commit()
        c.close_admission()
        op = c.begin(owners[0], "retire")
        self.assertFalse(c.retire(op, "producers", "failed"))
        first = c.first_error
        self.reject(c, "producer-live", lambda: c.retire(op, "hsl"))
        self.assertEqual(first, c.first_error)
        self.assertTrue(c.cells[0].prefix)

    def test_unknown_is_not_cleanup_permission(self):
        c, owners = prepare()
        c.close_admission()
        op = c.begin(owners[0], "retire")
        self.assertFalse(c.retire(op, "producers", "unknown"))
        self.reject(c, "not-retire-owned", lambda: c.retire(op, "producers"))
        self.assertFalse(c.module_exit_ready())

    def test_busy_retry_vs_unknown_prefix(self):
        for result in ("busy", "unknown"):
            c, owners = prepare()
            c.commit()
            c.close_admission()
            retire_consumer(c, owners[0])
            self.assertFalse(c.finish_prefix(result))
            self.assertTrue(c.registered and c.published)
            op = c.begin(owners[0], "retire")
            self.reject(c, "platform-too-early", lambda: c.retire(op, "platform"))
            c.end(op)
            if result == "unknown":
                self.reject(c, "prefix-unknown", c.finish_prefix)
            else:
                finish(c, owners)

    def test_global_publication_replacement_not_clobbered(self):
        c, owners = prepare(requested={"header_reg_get": CALLBACK})
        c.commit()
        c.close_admission()
        retire_consumer(c, owners[0])
        c.publication["header_reg_get"] = Callback("bytes", "replacement")
        self.reject(c, "publication-replaced", c.finish_prefix)

    def test_publication_replacement_before_commit(self):
        c, owners = prepare(requested={"header_reg_get": CALLBACK})
        c.publication["header_reg_get"] = Callback("bytes", "foreign")
        self.reject(c, "publication-replaced", c.commit)

    def test_publication_replacement_before_unpublished_abort(self):
        c, owners = prepare(requested={"header_reg_get": CALLBACK})
        c.publication["header_reg_get"] = Callback("bytes", "foreign")
        c.close_admission()
        retire_consumer(c, owners[0])
        self.reject(c, "publication-replaced", c.finish_prefix)

    def test_publication_replacement_before_reader(self):
        c, owners = prepare(requested={"header_reg_get": CALLBACK})
        c.commit()
        reader = c.get(0, "sd", "header_reg_get")
        self.assertEqual((reader.field, reader.callback), ("header_reg_get", CALLBACK))
        c.publication["header_reg_get"] = Callback("bytes", "foreign")
        self.reject(c, "publication-replaced", lambda: c.get(0, "sd", "header_reg_get"))
        # The admitted reader captured its prior view; external takeover is NOT authorized.
        self.assertEqual(reader.callback, CALLBACK)
        c.put(reader)

    def test_one_shot_selected_keeps_required_hsl(self):
        for selected in (("hsl",), ["hsl"], iter(("hsl",))):
            c = Cohort()
            c.start()
            owner = c.reserve(0, selected=selected)
            self.assertEqual(c.cells[0].selected, frozenset(("hsl",)))
            op = c.begin(owner, "construct")
            c.record(op, "platform")
            c.prefix(op, {})
            c.end(op)
            self.reject(c, "not-root-ready", c.commit)

    def test_internal_operation_cannot_revive_retired_hsl(self):
        c, owners = prepare()
        c.close_admission()
        op = c.begin(owners[0], "retire")
        c.retire(op, "producers")
        c.retire(op, "hsl")
        self.reject(c, "hsl-not-ready", lambda: c.get(0, "fal", operation=op))
        c.retire(op, "phy")
        self.reject(c, "phy-not-held", lambda: c.get(0, "phy", operation=op))

    def test_optional_union_complete_cycle_and_context(self):
        c, owners = prepare(requested={"header_reg_get": CALLBACK})
        second = c.reserve(1)
        owners.append(second)
        op = c.begin(second, "construct")
        c.record(op, "platform")
        added = Callback("indexed_bytes", "uniphy")
        c.prefix(op, {"uniphy_reg_get": added})
        c.certify_context(op, ("uniphy_reg_get", "header_reg_get"))
        for stage in SELECTED:
            if stage == "phy":
                c.claim_phy_ref(op, "borrowed")
            c.record(op, stage)
        c.end(op)
        c.commit()
        reader = c.get(1, "sd", "uniphy_reg_get")
        self.assertEqual(reader.callback, added)
        self.reject(c, "provider-not-ready", lambda: c.get(0, "sd", "uniphy_reg_get"))
        c.put(reader)
        c.close_admission()
        for owner in reversed(owners):
            retire_consumer(c, owner)
        finish(c, owners)
        self.assertEqual(c.publication, c.baseline)

    def test_multiple_phy_types_and_borrowed_table(self):
        c = Cohort(borrowed_phy_types=("external",))
        c.start()
        owners = []
        for i, phy_type in enumerate(("new-a", "external", "new-b")):
            owner = c.reserve(i, SELECTED, phy_type)
            owners.append(owner)
            op = c.begin(owner, "construct")
            c.record(op, "platform")
            c.prefix(op, {})
            for stage in SELECTED:
                if stage == "phy":
                    c.claim_phy_ref(op, "borrowed" if phy_type == "external" else "new")
                c.record(op, stage)
            c.end(op)
        c.commit()
        c.close_admission()
        for i in (1, 2, 0):
            retire_consumer(c, owners[i])
            self.assertEqual(c.phy_frees, [])
        finish(c, owners)
        self.assertEqual(c.phy_frees, ["new-a", "new-b"])

    def test_constructor_unknown_blocks_all_final_cleanup(self):
        c = Cohort()
        c.start()
        owner = c.reserve(0)
        op = c.begin(owner, "construct")
        c.record(op, "platform")
        self.assertFalse(c.prefix(op, {}, "unknown"))
        c.end(op)
        c.close_admission()
        self.reject(c, "residual-stage", c.finish_prefix)
        self.assertFalse(c.module_exit_ready())

    def test_borrowed_callbacks_phy_and_maps_not_freed(self):
        c = Cohort({"header_reg_get": CALLBACK}, borrowed_phy_types=("common",))
        c, owners = prepare(cohort=c)
        c.cells[0].status["platform"] = "borrowed"  # Explicit borrowed resource oracle.
        c.commit()
        c.close_admission()
        retire_consumer(c, owners[0])
        finish(c, owners)
        self.assertEqual(c.publication["header_reg_get"], CALLBACK)
        self.assertEqual(c.phy_frees, [])
        self.assertEqual(c.unmap_count, 0)

    def test_reader_identity_and_duplicate_put(self):
        c, owners = prepare()
        c.commit()
        reader = c.get(0, "uk")
        self.reject(c, "reader-identity", lambda: c.put(replace(reader, kind="fal")))
        c.put(reader)
        self.reject(c, "reader-identity", lambda: c.put(reader))

    def test_stale_owner_and_operation(self):
        c, owners = prepare()
        c.close_admission()
        retire_consumer(c, owners[0])
        finish(c, owners)
        c, fresh = prepare(cohort=c)
        self.assertNotEqual(owners[0], fresh[0])
        self.reject(c, "owner-epoch", lambda: c.begin(owners[0], "construct"))
        self.assertEqual(c.native_mutex_initializations, 1)

    def test_root_return_waits_for_platform_suffix(self):
        c, owners = prepare()
        c.commit()
        c.close_admission()
        retire_consumer(c, owners[0])
        c.finish_prefix()
        self.assertFalse(c.module_exit_ready())
        self.reject(c, "root-held", c.finish_root)
        op = c.begin(owners[0], "retire")
        c.retire(op, "platform")
        c.release_cell(op)
        c.finish_root()
        self.assertTrue(c.module_exit_ready())

    def test_no_false_phy_success_after_fal_failure(self):
        c = Cohort()
        c.start()
        owner = c.reserve(0)
        op = c.begin(owner, "construct")
        c.record(op, "platform")
        c.prefix(op, {})
        c.record(op, "hsl", "failed-clean")
        self.reject(c, "constructor-dependency", lambda: c.record(op, "phy"))
        c.end(op)
        self.reject(c, "not-root-ready", c.commit)
        self.assertEqual(c.first_error, "hsl:failed-clean")

    def test_namespaces_do_not_wrap(self):
        c = Cohort()
        c.epoch = MAX
        self.reject(c, "epoch-exhausted", c.start)
        c, owners = prepare()
        c.op_serial = MAX
        self.reject(c, "operation-exhausted", lambda: c.begin(owners[0], "construct"))
        c.commit()
        c.read_serial = MAX - 1
        reader = c.get(0, "uk")
        self.reject(c, "reader-exhausted", lambda: c.get(0, "uk"))
        c.put(reader)


NAMES = (
    "all_reader_classes_block_teardown", "borrowed_callbacks_phy_and_maps_not_freed",
    "busy_retry_vs_unknown_prefix", "conflict_and_type_are_preflight",
    "constructor_unknown_blocks_all_final_cleanup",
    "explicit_internal_continuation", "failed_prefix_keeps_peer_private_state",
    "failure_retains_owner_and_first_error", "foreign_uk_not_adopted",
    "global_publication_replacement_not_clobbered", "hsl_done_does_not_drop_late_stages",
    "internal_operation_cannot_revive_retired_hsl",
    "last_holder_all_three_orders", "multiple_phy_types_and_borrowed_table",
    "namespaces_do_not_wrap", "no_false_phy_success_after_fal_failure",
    "one_shot_selected_keeps_required_hsl", "optional_union_complete_cycle_and_context",
    "optional_union_null_inheritance",
    "private_public_readiness", "producer_and_sfp_order",
    "provider_context_not_callback_presence", "publication_replacement_before_commit",
    "publication_replacement_before_reader", "publication_replacement_before_unpublished_abort",
    "reader_identity_and_duplicate_put",
    "reservation_is_not_acquisition", "root_return_waits_for_platform_suffix",
    "sfp_before_phy_for_all_unresolved_states", "stale_owner_and_operation",
    "unknown_is_not_cleanup_permission",
)


if __name__ == "__main__":
    expected = ["test_" + name for name in NAMES]
    actual = unittest.defaultTestLoader.getTestCaseNames(Contracts)
    if actual != expected or len(expected) != 31:
        raise RuntimeError("FIXED_CONTRACT_TEST_INVENTORY")
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    print(json.dumps({"qualification": "SEQUENTIAL_DESIGN_MODEL_NOT_PRODUCTION_REPAIR",
                      "tests": result.testsRun, "inventory": expected,
                      "failures": len(result.failures), "errors": len(result.errors),
                      "success": result.wasSuccessful(), "raw_unittest": stream.getvalue()}))
    sys.exit(0 if result.wasSuccessful() and result.testsRun == 31 else 1)
