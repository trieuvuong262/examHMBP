from nas_storage.models import NasShareFolder
from nas_storage.nas_acl_apply import apply_folder_permissions, _run_ssh_commands, parse_synoshare_list_acl
for share in ["10_HE_THONG_CNTT","00_QUY_DINH_CHUNG","80_DUNG_CHUNG_LIEN_PHONG_BAN","90_MAU_BIEU_FORM_CHUAN"]:
    f = NasShareFolder.objects.filter(share_name=share, parent__isnull=True).first()
    if f:
        print(share, apply_folder_permissions(f))
    out = _run_ssh_commands(["/usr/syno/sbin/synoshare --list_acl "+share])
    c = parse_synoshare_list_acl(out)
    print(" NAS RW", sorted(c.get("RW",[])))