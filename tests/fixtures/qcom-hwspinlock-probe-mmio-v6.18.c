// SPDX-License-Identifier: GPL-2.0
/*
 * Exact Linux v6.18 qcom_hwspinlock_probe_mmio() excerpt used to verify the
 * OpenWrt kernel patch without requiring network access during tests.
 */
static struct regmap *qcom_hwspinlock_probe_mmio(struct platform_device *pdev,
						 u32 *offset, u32 *stride)
{
	const struct qcom_hwspinlock_of_data *data;
	struct device *dev = &pdev->dev;
	void __iomem *base;

	data = of_device_get_match_data(dev);
	if (!data->regmap_config)
		return ERR_PTR(-EINVAL);

	*offset = data->offset;
	*stride = data->stride;

	base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(base))
		return ERR_CAST(base);

	return devm_regmap_init_mmio(dev, base, data->regmap_config);
}
