static int ssdk_probe(struct platform_device *pdev)
{
	struct device_node *np;
	struct ssdk_driver_priv *priv = NULL;

	np = of_node_get(pdev->dev.of_node);
	if (of_device_is_compatible(np, "qcom,ess-instance"))
		return of_platform_populate(np, NULL, NULL, &pdev->dev);

	priv = devm_kzalloc(&pdev->dev, sizeof(*priv), GFP_KERNEL);
	of_property_read_u32(np, "device_id", &(priv->dev_id));
	platform_set_drvdata(pdev, priv);

	return 0;
}
