#!/usr/bin/env python3

import bbki

hostInfo = bbki.HostInfo("native", "native")
cfg = bbki.EtcDirConfig(cfgdir="./test.cfg")

obj = bbki.Bbki(hostInfo, cfg=cfg)
obj.config
obj.repositories
obj.rescue_os_spec
obj.check_running_environment()
obj.get_current_boot_entry()
obj.get_pending_boot_entry()
obj.has_rescue_os()
obj.get_kernel_atom()
obj.get_kernel_addon_atoms()

