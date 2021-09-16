
class BbkiAtomDb:

    @staticmethod
    def getAllAtomDb(bbki):
        ret = []
        for lv1 in os.listdir(self._bbki.config.db_dir):
            for lv2 in os.listdir(os.path.join(self._bbki.config.db_dir, lv1)):
                ret.append(BbkiAtomDb(bbki, os.path.join(lv1, lv2)))
        return ret

    def __init__(self, bbki, atom_fullname):
        self._bbki = bbki
        self._atomFullname = atom_fullname
        self._kernelType, self._atomType = _parse_catdir(atom_fullname.split("/")[0])

        self._dbDir = os.path.join(self._bbki.config.db_dir, self._atomFullname)
        self._firmwareExtFilePath = os.path.join(self._dbDir, "FIRMWARE_EXTFILE")

    @property
    def kernel_type(self):
        return self._kernelType

    @property
    def atom_type(self):
        return self._atomType

    @property
    def name(self):
        return self._name

    @property
    def fullname(self):
        return os.path.join(_format_catdir(self._kernelType, self._atomType), self._name)

    @property
    def ver(self):
        return self._ver

    @property
    def rev(self):
        return self._rev

    @property
    def verstr(self):
        if self.rev == 0:
            return self.ver
        else:
            return self.ver + "-r" + self.rev



    @property
    def db_dir(self):
        return self._dbDir

    def create(self):
        robust_layer.simple_fops.mk_empty_dir(self._dbDir)

        if self._atomType == Repo.ATOM_TYPE_KERNEL:
            pass
        elif self._atomType == Repo.ATOM_TYPE_KERNEL_ADDON:
            with open(self._firmwareExtFilePath, "w") as f:
                f.write("")
        elif self._atomType == Repo.ATOM_TYPE_INITRAMFS:
            pass
        else:
            assert False

    def remove(self):
        robust_layer.simple_fops.rm(self._dbDir)

    def add_firmware_extfile(self, filename):
        assert self._atomType == Repo.ATOM_TYPE_KERNEL_ADDON
        Util.addItemToListFile(filename, self._firmwareExtFilePath)

    def get_firmware_extfiles(self):
        assert self._atomType == Repo.ATOM_TYPE_KERNEL_ADDON
        return Util.readListFile(self._firmwareExtFilePath)
