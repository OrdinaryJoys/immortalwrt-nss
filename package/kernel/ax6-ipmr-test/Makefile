include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=kmod-ax6-ipmr-test
PKG_RELEASE:=1

include $(INCLUDE_DIR)/package.mk

define KernelPackage/ax6-ipmr-test
  SUBMENU:=Other modules
  TITLE:=AX6 ipmr MFC callback probe
  FILES:=$(PKG_BUILD_DIR)/ax6_ipmr_test.ko
  AUTOLOAD:=$(call AutoProbe,ax6_ipmr_test)
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
	$(CP) ./src/* $(PKG_BUILD_DIR)/
endef

define Build/Compile
	$(MAKE) -C "$(LINUX_DIR)" \
		ARCH="$(LINUX_KARCH)" \
		CROSS_COMPILE="$(TARGET_CROSS)" \
		M="$(PKG_BUILD_DIR)" modules
endef

$(eval $(call KernelPackage,ax6-ipmr-test))
