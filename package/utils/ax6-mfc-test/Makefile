include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=ax6-mfc-test
PKG_RELEASE:=1
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)

include $(INCLUDE_DIR)/package.mk

define Package/ax6-mfc-test
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=AX6 MFC add/delete probe
  DEPENDS:=+libc
endef

define Package/ax6-mfc-test/description
  Add and delete IPv4 multicast forwarding entries to exercise the
  QCA 0604-1 ipmr MFC event offload callback.
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) -I$(LINUX_DIR)/usr/include \
		-o $(PKG_BUILD_DIR)/ax6-mfc-test ./src/ax6-mfc-test.c
endef

define Package/ax6-mfc-test/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/ax6-mfc-test $(1)/usr/sbin/ax6-mfc-test
endef

$(eval $(call BuildPackage,ax6-mfc-test))
