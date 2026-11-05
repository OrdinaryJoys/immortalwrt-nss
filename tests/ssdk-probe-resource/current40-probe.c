static int ssdk_probe(struct platform_device *pdev)
{
	struct device_node *np;
	struct ssdk_driver_priv *priv = NULL;
	int rv;

	np = of_node_get(pdev->dev.of_node);
	if (of_device_is_compatible(np, "qcom,ess-instance")) {
		rv = of_platform_populate(np, NULL, NULL, &pdev->dev);
		goto out;
	}

	priv = devm_kzalloc(&pdev->dev, sizeof(*priv), GFP_KERNEL);
	if (!priv) {
		rv = -ENOMEM;
		goto out;
	}
	of_property_read_u32(np, "device_id", &(priv->dev_id));
	platform_set_drvdata(pdev, priv);
	rv = 0;

out:
	of_node_put(np);
	return rv;
}
