from hrm.permissions import (
    can_edit_user_guide,
    can_view_team_reports,
    is_gm,
    is_hod,
    is_manager,
    is_portal_admin,
    is_team_leader,
    is_division_head,
    role_display,
    user_role,
)


def portal_permissions(request):
    user = request.user
    if not user.is_authenticated:
        return {
            'jp_can_portal_admin': False,
            'jp_can_edit_guide': False,
            'jp_is_hod': False,
            'jp_is_gm': False,
            'jp_is_team_leader': False,
            'jp_is_division_head': False,
            'jp_is_manager': False,
            'jp_can_team_reports': False,
            'jp_user_role': '',
            'jp_role_display': '',
        }
    return {
        'jp_can_portal_admin': is_portal_admin(user),
        'jp_can_edit_guide': can_edit_user_guide(user),
        'jp_is_hod': is_hod(user),
        'jp_is_gm': is_gm(user),
        'jp_is_team_leader': is_team_leader(user),
        'jp_is_division_head': is_division_head(user),
        'jp_is_manager': is_manager(user),
        'jp_can_team_reports': can_view_team_reports(user),
        'jp_user_role': user_role(user),
        'jp_role_display': role_display(user),
    }
