// SPDX-License-Identifier: GPL-2.0
/*
 * Minimal consumer for the 0604-1 QCA ipmr MFC event offload API.
 * It only observes update/delete events; it never sleeps in the callback.
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/mroute.h>
#include <linux/in.h>
#include <linux/atomic.h>

static atomic_t ax6_events = ATOMIC_INIT(0);
static atomic_t ax6_updates = ATOMIC_INIT(0);
static atomic_t ax6_deletes = ATOMIC_INIT(0);

static void ax6_ipmr_event(__be32 origin, __be32 group, u32 dest_count,
			   u32 dest_dev[], u8 op)
{
	atomic_inc(&ax6_events);
	if (op == IPMR_MFC_EVENT_UPDATE)
		atomic_inc(&ax6_updates);
	else if (op == IPMR_MFC_EVENT_DELETE)
		atomic_inc(&ax6_deletes);

	pr_info("AX6_IPMR_TEST event=%u origin=%pI4 group=%pI4 dest_count=%u first_dev=%u\n",
		op, &origin, &group, dest_count,
		dest_count && dest_dev ? dest_dev[0] : 0);
}

static int __init ax6_ipmr_test_init(void)
{
	if (!ipmr_register_mfc_event_offload_callback(ax6_ipmr_event)) {
		pr_err("AX6_IPMR_TEST register failed (another consumer active)\n");
		return -EBUSY;
	}

	pr_info("AX6_IPMR_TEST registered\n");
	return 0;
}

static void __exit ax6_ipmr_test_exit(void)
{
	ipmr_unregister_mfc_event_offload_callback();
	pr_info("AX6_IPMR_TEST unregistered events=%d updates=%d deletes=%d\n",
		atomic_read(&ax6_events), atomic_read(&ax6_updates),
		atomic_read(&ax6_deletes));
}

module_init(ax6_ipmr_test_init);
module_exit(ax6_ipmr_test_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("AX6 test harness");
MODULE_DESCRIPTION("AX6 0604 ipmr MFC callback probe");
MODULE_ALIAS("ax6-ipmr-test");
