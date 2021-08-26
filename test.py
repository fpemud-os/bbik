#!/usr/bin/env python3

import bbki

cfg = bbki.EtcDirConfig(cfgdir="./test-cfg")

obj = bbki.Bbki(cfg=cfg)
obj.config
obj.repositories
obj.rescue_os_spec
obj.check_running_environment()
obj.get_current_boot_entry()
obj.get_pending_boot_entry()
obj.has_rescue_os()
obj.get_kernel_atom()
obj.get_kernel_addon_atoms()
obj.check()
