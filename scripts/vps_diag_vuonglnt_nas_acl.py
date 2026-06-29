from django.contrib.auth import get_user_model
from nas_storage.models import NasFolderPermission, NasShareFolder
from nas_storage.download_shares import nas_webdav_shares_for_user
from nas_storage.nas_acl_apply import _desired_share_acl_buckets, _run_ssh_commands, apply_folder_permissions, parse_synoshare_list_acl
u = get_user_model().objects.filter(username__iexact="Vuonglnt").first()
print("user", u.username)
print("shares", nas_webdav_shares_for_user(u))
for share in nas_webdav_shares_for_user(u):
    f = NasShareFolder.objects.filter(share_name=share, parent__isnull=True).first()
    print("---", share)
    for p in NasFolderPermission.objects.filter(folder=f).select_related("user", "group"):
        print(" perm", p.resolved_nas_principal(), p.access_level_label())
    d = _desired_share_acl_buckets(f)
    print(" want RW", sorted(d.get("RW", set())))
    out = _run_ssh_commands(["/usr/syno/sbin/synoshare --list_acl " + share])
    c = parse_synoshare_list_acl(out)
    print(" nas RW", sorted(c.get("RW", set())))
    r = apply_folder_permissions(f)
    print(" apply", r)