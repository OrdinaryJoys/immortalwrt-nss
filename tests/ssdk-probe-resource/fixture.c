#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define GFP_KERNEL 0
typedef uint32_t a_uint32_t;
struct device_node { int refs; int instance; int has_id; uint32_t id; };
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; void *drvdata; };
struct ssdk_driver_priv { a_uint32_t dev_id; };
struct input { int node; int instance; int has_id; uint32_t id; int oom; int populate_rc; };
static const struct input cases[] = {
    {1, 0, 1, 0, 0, 0}, {1, 0, 1, 7, 0, 0},
    {1, 0, 0, 99, 0, 0}, {0, 0, 0, 99, 0, 0},
    {1, 0, 1, UINT32_MAX, 0, 0},
    {1, 0, 1, 2, 1, 0}, {0, 0, 0, 0, 1, 0},
    {1, 1, 1, 7, 0, 0}, {1, 1, 1, 7, 0, -ENOMEM},
    {1, 1, 1, 7, 0, -517}, {1, 1, 1, 7, 0, -EINVAL},
    {1, 1, 1, 7, 1, 0}
};
static const struct input *input;
static struct device_node node;
static struct platform_device device;
static void *allocation;
static int get_calls, put_calls, allocs, properties, publishes, populates;

static void fail(const char *marker)
{
    fprintf(stderr, "PROBE:%s\n", marker);
    exit(86);
}
static void need(int condition, const char *marker)
{
    if (!condition) fail(marker);
}
static struct device_node *of_node_get(struct device_node *np)
{
    get_calls++;
    if (np) np->refs++;
    return np;
}
static void of_node_put(struct device_node *np)
{
    put_calls++;
    if (np) {
        np->refs--;
        need(np->refs >= 1, "NODE_REF");
    }
}
static int of_device_is_compatible(const struct device_node *np, const char *name)
{
    need(strcmp(name, "qcom,ess-instance") == 0, "MATCH_NAME");
    return np && np->instance;
}
static int of_platform_populate(struct device_node *np, const void *matches,
                               const void *auxdata, struct device *parent)
{
    need(np == device.dev.of_node && parent == &device.dev && !matches && !auxdata,
         "POPULATE_ARGUMENTS");
    populates++;
    return input->populate_rc;
}
static void *devm_kzalloc(struct device *dev, size_t size, int flags)
{
    need(dev == &device.dev && size == sizeof(struct ssdk_driver_priv) &&
         flags == GFP_KERNEL && !allocation, "ALLOCATION_ARGUMENTS");
    allocs++;
    if (input->oom) return NULL;
    allocation = calloc(1, size);
    need(allocation != NULL, "HOST_ALLOCATION");
    return allocation;
}
static int model_of_property_read_u32(const struct device_node *np, const char *name, uint32_t *out)
{
    /* Detect the actual null-private dependency without invoking host UB. */
    need(allocation != NULL, "NULL_PRIVATE");
    need(out == &((struct ssdk_driver_priv *)allocation)->dev_id &&
         strcmp(name, "device_id") == 0, "PROPERTY_ARGUMENTS");
    properties++;
    if (!np || !np->has_id) return -EINVAL;
    *out = np->id;
    return 0;
}
/* Check the call boundary before forming a null member address in old code. */
#define of_property_read_u32(np, name, out) \
    (need(allocation != NULL, "NULL_PRIVATE"), model_of_property_read_u32((np), (name), (out)))
static void platform_set_drvdata(struct platform_device *pdev, void *priv)
{
    need(pdev == &device && priv != NULL && priv == allocation, "PUBLISH_ARGUMENTS");
    device.drvdata = priv;
    publishes++;
}

#include "actual.c"

int main(int argc, char **argv)
{
    char *end = NULL;
    need(argc == 2, "CASE_ARGUMENT");
    unsigned long index = strtoul(argv[1], &end, 10);
    need(end && *end == '\0' && index < sizeof(cases) / sizeof(cases[0]), "CASE_ARGUMENT");
    input = &cases[index];
    node = (struct device_node){1, input->instance, input->has_id, input->id};
    device.dev.of_node = input->node ? &node : NULL;
    int instance = input->node && input->instance;
    int rc = ssdk_probe(&device);
    int expected = instance ? input->populate_rc : input->oom ? -ENOMEM : 0;
    need(rc == expected, "RETURN_VALUE");
    need(node.refs == 1 && get_calls == 1 && put_calls == 1, "NODE_REF");
    need(populates == instance && allocs == !instance, "ACQUISITION_PATH");
    if (instance || input->oom) {
        need(!device.drvdata && !allocation && !properties && !publishes,
             "FAILED_OR_INSTANCE_PUBLICATION");
    } else {
        need(device.drvdata == allocation && device.drvdata && publishes == 1,
             "PUBLISHED_POINTER");
        need(properties == 1, "PROPERTY_PATH");
        uint32_t id = input->node && input->has_id ? input->id : 0;
        need(((struct ssdk_driver_priv *)device.drvdata)->dev_id == id, "DEVICE_ID");
    }
    /* Model devres teardown only after the complete probe has returned. */
    free(allocation);
    puts("PROBE:PASS");
    return 0;
}
