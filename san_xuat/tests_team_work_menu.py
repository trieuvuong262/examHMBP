from django.contrib.auth.models import User
from django.test import TestCase

from hrm.models import Department, Division, PermissionGroup, Profile, ProfileConcurrentPosition
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from san_xuat.services.team_division_map import (
    can_see_all_team_work_teams,
    team_slug_for_division_id,
    team_work_menu_items,
    user_can_open_team_work_slug,
    user_led_team_division_ids,
)


def _sx_group():
    group, _ = PermissionGroup.objects.get_or_create(
        slug='sx-xem-tw-menu',
        defaults={
            'name': 'SX xem tw menu',
            'module_permissions': {
                'san_xuat': {
                    'view': True,
                    'create': False,
                    'update': False,
                    'delete': False,
                    'export': False,
                },
            },
        },
    )
    return group


def _user(username, *, role=ROLE_EMPLOYEE, department=None, division=None, job_position='', group=None):
    user, created = User.objects.get_or_create(username=username, defaults={'password': 'x'})
    if created:
        user.set_password('x')
        user.save()
    profile = Profile.objects.get(user=user)
    profile.full_name = username
    profile.role = role
    profile.department = department
    profile.division = division
    if job_position:
        profile.job_position = job_position
    if group is not None:
        profile.permission_group = group
    profile.save()
    user.profile = profile
    return user


class TeamWorkMenuLeaderTests(TestCase):
    def setUp(self):
        self.dept, _ = Department.objects.get_or_create(name='SẢN XUẤT', defaults={'is_active': True})
        self.dept.is_active = True
        self.dept.save(update_fields=['is_active'])
        self.div_may, _ = Division.objects.get_or_create(
            department=self.dept, name='May TW Menu', defaults={'is_active': True},
        )
        self.div_cat, _ = Division.objects.get_or_create(
            department=self.dept, name='Cat TW Menu', defaults={'is_active': True},
        )
        self.group = _sx_group()
        self.leader_may = _user(
            'tt.may.twmenu',
            role=ROLE_TEAM_LEADER,
            department=self.dept,
            division=self.div_may,
            job_position='To truong',
            group=self.group,
        )
        self.leader_cat = _user(
            'tt.cat.twmenu',
            role=ROLE_TEAM_LEADER,
            department=self.dept,
            division=self.div_cat,
            job_position='To truong',
            group=self.group,
        )
        self.worker = _user(
            'cn.may.twmenu',
            role=ROLE_EMPLOYEE,
            department=self.dept,
            division=self.div_may,
            group=self.group,
        )

    def test_team_leader_sees_only_own_division(self):
        slugs = [i['slug'] for i in team_work_menu_items(self.leader_may)]
        self.assertEqual(slugs, [team_slug_for_division_id(self.div_may.pk)])
        self.assertTrue(user_can_open_team_work_slug(self.leader_may, slugs[0]))
        self.assertFalse(
            user_can_open_team_work_slug(self.leader_may, team_slug_for_division_id(self.div_cat.pk)),
        )

    def test_worker_sees_no_team(self):
        self.assertEqual(team_work_menu_items(self.worker), [])
        self.assertEqual(user_led_team_division_ids(self.worker), set())

    def test_concurrent_team_leader_sees_extra_division(self):
        slot, _ = ProfileConcurrentPosition.objects.get_or_create(
            profile=self.leader_may.profile,
            department=self.dept,
            division=self.div_cat,
            job_position='To truong',
            defaults={'role': ROLE_TEAM_LEADER, 'is_active': True},
        )
        slot.role = ROLE_TEAM_LEADER
        slot.is_active = True
        slot.save(update_fields=['role', 'is_active'])
        slugs = {i['slug'] for i in team_work_menu_items(self.leader_may)}
        self.assertEqual(
            slugs,
            {
                team_slug_for_division_id(self.div_may.pk),
                team_slug_for_division_id(self.div_cat.pk),
            },
        )

    def test_admin_and_ductn_see_all(self):
        admin = _user('admin', group=self.group)
        ductn = _user('Ductn', group=self.group)
        self.assertTrue(can_see_all_team_work_teams(admin))
        self.assertTrue(can_see_all_team_work_teams(ductn))
        admin_slugs = {i['slug'] for i in team_work_menu_items(admin)}
        ductn_slugs = {i['slug'] for i in team_work_menu_items(ductn)}
        self.assertIn(team_slug_for_division_id(self.div_may.pk), admin_slugs)
        self.assertIn(team_slug_for_division_id(self.div_cat.pk), admin_slugs)
        self.assertEqual(admin_slugs, ductn_slugs)
        self.assertTrue(
            user_can_open_team_work_slug(admin, team_slug_for_division_id(self.div_cat.pk)),
        )
