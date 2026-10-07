"""Quy tắc luồng Tuyển dụng: đánh giá quản lý, phỏng vấn 1 vòng, onboard, nháp từ đề xuất."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, PermissionGroup, Profile
from hrm.permissions import ROLE_DEPARTMENT_HEAD, ROLE_DIRECTOR, ROLE_EMPLOYEE
from recruitment import services
from recruitment.models import Candidate, CandidateEvent, CandidateReview, Interview, JobPosting

FULL = {'view': True, 'create': True, 'update': True, 'delete': True, 'export': True, 'print': False}
NONE = {k: False for k in FULL}


def _group(slug, *, hrm_users_create=True, all_departments=True):
    return PermissionGroup.objects.create(
        slug=slug,
        name=slug,
        module_permissions={
            'recruitment': {
                **FULL, 'menus': {'candidates': dict(FULL), 'jobs': dict(FULL)},
                'extras': {'all_departments': all_departments},
            },
            'hrm': {
                **FULL,
                'menus': {
                    'users': {**FULL, 'create': hrm_users_create},
                    'locked_accounts': dict(NONE),
                },
            },
        },
    )


def _user(username, *, role=ROLE_EMPLOYEE, department=None, group=None):
    user = User.objects.create_user(username=username, password='x')
    Profile.objects.filter(user=user).update(
        role=role, department=department, permission_group=group, full_name=username, is_employed=True,
    )
    user.refresh_from_db()
    return user


class RecruitmentFlowBase(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Xưởng May RC', sort_order=1)
        self.other_dept = Department.objects.create(name='Kế toán RC', sort_order=2)
        self.hr = _user('rc_hr', group=_group('rc-hr'))
        self.manager = _user('rc_tp', role=ROLE_DEPARTMENT_HEAD, department=self.dept)
        self.other_manager = _user('rc_tp_other', role=ROLE_DEPARTMENT_HEAD, department=self.other_dept)
        self.director = _user('rc_gd', role=ROLE_DIRECTOR)
        self.employee = _user('rc_nv', department=self.dept)
        self.job = JobPosting.objects.create(
            title='Công nhân may chuyền 2', target_department=self.dept, position='Công nhân may',
            quantity=1, description='May áo thun', deadline=timezone.localdate() + timedelta(days=10),
            status=JobPosting.STATUS_OPEN,
        )

    def _candidate(self, name='Nguyễn Văn A', phone='0901000001', **kw):
        return services.add_candidate(
            self.job, services.CandidateInput(full_name=name, phone=phone, **kw), actor=self.hr,
        )

    def _to_interview(self, cand):
        services.transition(cand, Candidate.STATUS_REVIEWING, actor=self.hr)
        services.submit_review(cand, self.manager, decision=CandidateReview.DECISION_RECOMMEND, rating=4)
        services.transition(
            cand, Candidate.STATUS_INTERVIEWING, actor=self.hr,
            interview_time=timezone.now() - timedelta(hours=1), location='Phòng HR',
        )
        cand.refresh_from_db()
        return cand


class TransitionRuleTests(RecruitmentFlowBase):
    def test_cannot_skip_steps(self):
        cand = self._candidate()
        with self.assertRaises(services.RecruitmentError):
            services.transition(cand, Candidate.STATUS_OFFERED, actor=self.hr)
        with self.assertRaises(services.RecruitmentError):
            services.transition(cand, Candidate.STATUS_INTERVIEWING, actor=self.hr)

    def test_interview_requires_manager_recommendation_and_time(self):
        cand = self._candidate()
        services.transition(cand, Candidate.STATUS_REVIEWING, actor=self.hr)
        with self.assertRaisesMessage(services.RecruitmentError, 'Đề xuất phỏng vấn'):
            services.transition(cand, Candidate.STATUS_INTERVIEWING, actor=self.hr,
                                interview_time=timezone.now())
        services.submit_review(cand, self.manager, decision=CandidateReview.DECISION_CONSIDER)
        with self.assertRaises(services.RecruitmentError):
            services.transition(cand, Candidate.STATUS_INTERVIEWING, actor=self.hr,
                                interview_time=timezone.now())
        services.submit_review(cand, self.manager, decision=CandidateReview.DECISION_RECOMMEND)
        with self.assertRaisesMessage(services.RecruitmentError, 'thời gian'):
            services.transition(cand, Candidate.STATUS_INTERVIEWING, actor=self.hr)
        services.transition(cand, Candidate.STATUS_INTERVIEWING, actor=self.hr,
                            interview_time=timezone.now() + timedelta(days=1))
        cand.refresh_from_db()
        self.assertEqual(cand.status, Candidate.STATUS_INTERVIEWING)
        self.assertEqual(cand.interview.result, Interview.RESULT_PENDING)

    def test_offer_requires_pass_and_capacity(self):
        cand = self._to_interview(self._candidate())
        with self.assertRaisesMessage(services.RecruitmentError, 'Đạt'):
            services.transition(cand, Candidate.STATUS_OFFERED, actor=self.hr)
        services.record_interview_result(cand, Interview.RESULT_PASS, 'Tay nghề tốt', actor=self.hr)
        services.transition(cand, Candidate.STATUS_OFFERED, actor=self.hr)

        second = self._to_interview(self._candidate('Trần B', '0901000002'))
        services.record_interview_result(second, Interview.RESULT_PASS, '', actor=self.hr)
        with self.assertRaisesMessage(services.RecruitmentError, 'đủ chỉ tiêu'):
            services.transition(second, Candidate.STATUS_OFFERED, actor=self.hr)

    def test_failed_interview_rejects_with_reason(self):
        cand = self._to_interview(self._candidate())
        with self.assertRaises(services.RecruitmentError):
            services.record_interview_result(cand, Interview.RESULT_FAIL, '', actor=self.hr)
        services.record_interview_result(cand, Interview.RESULT_FAIL, 'Không đạt tay nghề', actor=self.hr)
        cand.refresh_from_db()
        self.assertEqual(cand.status, Candidate.STATUS_REJECTED)
        self.assertIn('Không đạt tay nghề', cand.reject_reason)

    def test_result_not_before_interview_time(self):
        cand = self._candidate()
        services.transition(cand, Candidate.STATUS_REVIEWING, actor=self.hr)
        services.submit_review(cand, self.manager, decision=CandidateReview.DECISION_RECOMMEND)
        services.transition(cand, Candidate.STATUS_INTERVIEWING, actor=self.hr,
                            interview_time=timezone.now() + timedelta(hours=2))
        with self.assertRaisesMessage(services.RecruitmentError, 'Chưa tới giờ'):
            services.record_interview_result(cand, Interview.RESULT_PASS, '', actor=self.hr)

    def test_reject_requires_reason_and_can_reopen(self):
        cand = self._candidate()
        with self.assertRaises(services.RecruitmentError):
            services.transition(cand, Candidate.STATUS_REJECTED, actor=self.hr)
        services.transition(cand, Candidate.STATUS_REJECTED, actor=self.hr, reason='Sai vị trí')
        services.transition(cand, Candidate.STATUS_REVIEWING, actor=self.hr)
        cand.refresh_from_db()
        self.assertEqual(cand.reject_reason, '')

    def test_hired_only_via_onboard(self):
        cand = self._candidate()
        with self.assertRaisesMessage(services.RecruitmentError, 'Onboard'):
            services.transition(cand, Candidate.STATUS_HIRED, actor=self.hr)

    def test_history_logged(self):
        cand = self._to_interview(self._candidate())
        kinds = list(cand.events.values_list('kind', flat=True))
        self.assertIn(CandidateEvent.KIND_CREATED, kinds)
        self.assertIn(CandidateEvent.KIND_REVIEW, kinds)
        self.assertEqual(kinds.count(CandidateEvent.KIND_STATUS), 2)


class JobRuleTests(RecruitmentFlowBase):
    def test_closed_or_expired_job_rejects_candidates(self):
        self.job.status = JobPosting.STATUS_PAUSED
        self.job.save()
        with self.assertRaises(services.RecruitmentError):
            self._candidate()
        self.job.status = JobPosting.STATUS_OPEN
        self.job.deadline = timezone.localdate() - timedelta(days=1)
        self.job.save()
        with self.assertRaises(services.RecruitmentError):
            self._candidate()

    def test_duplicate_phone_blocked(self):
        self._candidate(phone='0901 000 001')
        with self.assertRaisesMessage(services.RecruitmentError, 'đã nộp'):
            self._candidate(name='Khác', phone='0901000001')

    def test_cannot_delete_job_with_candidates(self):
        self._candidate()
        with self.assertRaises(services.RecruitmentError):
            services.delete_job(self.job)

    def test_open_requires_department_deadline_description(self):
        draft = JobPosting.objects.create(title='Nháp', position='Công nhân may', status=JobPosting.STATUS_DRAFT)
        with self.assertRaisesMessage(services.RecruitmentError, 'phòng ban'):
            services.change_job_status(draft, JobPosting.STATUS_OPEN, actor=self.hr)


class ManagerReviewTests(RecruitmentFlowBase):
    def test_scope_by_department(self):
        cand = self._candidate()
        services.transition(cand, Candidate.STATUS_REVIEWING, actor=self.hr)
        with self.assertRaises(services.RecruitmentError):
            services.submit_review(cand, self.other_manager, decision=CandidateReview.DECISION_RECOMMEND)
        with self.assertRaises(services.RecruitmentError):
            services.submit_review(cand, self.employee, decision=CandidateReview.DECISION_RECOMMEND)
        services.submit_review(cand, self.director, decision=CandidateReview.DECISION_RECOMMEND)
        self.assertEqual(cand.reviews.count(), 1)

    def test_not_suitable_needs_comment_and_only_in_review_step(self):
        cand = self._candidate()
        with self.assertRaises(services.RecruitmentError):
            services.submit_review(cand, self.manager, decision=CandidateReview.DECISION_RECOMMEND)
        services.transition(cand, Candidate.STATUS_REVIEWING, actor=self.hr)
        with self.assertRaises(services.RecruitmentError):
            services.submit_review(cand, self.manager, decision=CandidateReview.DECISION_NOT_SUITABLE)

    def test_review_pages(self):
        cand = self._candidate()
        services.transition(cand, Candidate.STATUS_REVIEWING, actor=self.hr)
        client = Client(HTTP_HOST='testserver')

        client.force_login(self.employee)
        self.assertEqual(client.get(reverse('recruitment_review_list')).status_code, 302)

        client.force_login(self.other_manager)
        self.assertEqual(client.get(reverse('recruitment_review_candidate', args=[cand.pk])).status_code, 403)

        client.force_login(self.manager)
        resp = client.get(reverse('recruitment_review_list'))
        self.assertContains(resp, cand.full_name)
        resp = client.post(reverse('recruitment_review_candidate', args=[cand.pk]), {
            'decision': CandidateReview.DECISION_RECOMMEND, 'rating': '5', 'comment': 'Phù hợp',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(cand.reviews.filter(reviewer=self.manager, rating=5).exists())

    def test_manager_can_refer_candidate(self):
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.manager)
        resp = client.post(reverse('recruitment_refer_candidate'), {
            'job_posting': self.job.pk, 'full_name': 'Lê C', 'phone': '0912345678',
        })
        self.assertEqual(resp.status_code, 302)
        cand = Candidate.objects.get(full_name='Lê C')
        self.assertEqual(cand.source, Candidate.SOURCE_REFERRAL)
        self.assertEqual(cand.referred_by, self.manager)


class OnboardTests(RecruitmentFlowBase):
    def _offered(self):
        cand = self._to_interview(self._candidate(email='a.nguyen@example.com'))
        services.record_interview_result(cand, Interview.RESULT_PASS, '', actor=self.hr)
        return services.transition(cand, Candidate.STATUS_OFFERED, actor=self.hr)

    def test_onboard_creates_employee_with_code_group_and_course(self):
        from training.models import Course

        course = Course.objects.create(title='Đào tạo hội nhập', description='Onboarding', is_active=True)
        probation = PermissionGroup.objects.create(slug='rc-thu-viec', name='Nhân viên thử việc')
        cand = self._offered()

        result = services.onboard_candidate(cand, actor=self.hr)
        cand.refresh_from_db()
        profile = Profile.objects.get(user=result.user)
        self.assertEqual(cand.status, Candidate.STATUS_HIRED)
        self.assertEqual(cand.employee, result.user)
        self.assertEqual(profile.employee_code, result.employee_code)
        self.assertEqual(profile.department, self.dept)
        self.assertEqual(profile.permission_group, probation)
        self.assertTrue(profile.must_change_password)
        self.assertIn(result.user, course.assigned_users.all())
        with self.assertRaises(services.RecruitmentError):
            services.onboard_candidate(cand, actor=self.hr)

    def test_onboard_view_needs_hrm_create(self):
        cand = self._offered()
        no_hrm = _user('rc_hr_nohrm', group=_group('rc-hr-nohrm', hrm_users_create=False))
        client = Client(HTTP_HOST='testserver')
        client.force_login(no_hrm)
        client.post(reverse('candidate_onboard', args=[cand.pk]), {'join_date': timezone.localdate().isoformat()})
        cand.refresh_from_db()
        self.assertEqual(cand.status, Candidate.STATUS_OFFERED)

        client.force_login(self.hr)
        resp = client.post(reverse('candidate_onboard', args=[cand.pk]), {'join_date': timezone.localdate().isoformat()})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Cache-Control'], 'no-store')
        cand.refresh_from_db()
        self.assertEqual(cand.status, Candidate.STATUS_HIRED)


class ProposalDraftTests(RecruitmentFlowBase):
    def _proposal(self, hr_kind='Tuyển dụng'):
        from service_requests.models import RequestType, ServiceRequest

        rtype = RequestType.objects.create(code='general_proposal_rc', name='Đề xuất')
        return ServiceRequest.objects.create(
            requester=self.manager, request_type=rtype, request_subtype=ServiceRequest.SUBTYPE_HR,
            title='Tuyển công nhân may', description='Bổ sung chuyền 2',
            extra_data={
                'hr_kind': hr_kind, 'position': 'Công nhân may', 'target_department': self.dept.name,
                'headcount': 3, 'recruit_reason': 'Bổ sung', 'desired_date': '01/12/2026',
                'candidate_requirements': 'Biết may 1 kim',
            },
        )

    def test_completed_proposal_creates_single_draft(self):
        from service_requests.workflow import _maybe_complete_request

        req = self._proposal()
        self.assertTrue(_maybe_complete_request(req, actor=self.director))
        job = JobPosting.objects.get(service_request=req)
        self.assertEqual(job.status, JobPosting.STATUS_DRAFT)
        self.assertEqual(job.target_department, self.dept)
        self.assertEqual(job.quantity, 3)
        self.assertEqual(job.position, 'Công nhân may')
        self.assertEqual(job.deadline.isoformat(), '2026-12-01')
        services.create_draft_from_service_request(req)
        self.assertEqual(JobPosting.objects.filter(service_request=req).count(), 1)

    def test_transfer_proposal_creates_nothing(self):
        req = self._proposal(hr_kind='Điều chuyển')
        self.assertIsNone(services.create_draft_from_service_request(req))


class RecruitmentPageTests(RecruitmentFlowBase):
    def test_hr_pages_render(self):
        cand = self._to_interview(self._candidate())
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.hr)
        for url in (
            reverse('recruitment_overview'),
            reverse('job_posting_list'),
            reverse('job_posting_edit', args=[self.job.pk]),
            reverse('kanban_board'),
            reverse('add_candidate'),
            reverse('candidate_detail', args=[cand.pk]),
            reverse('interview_list'),
        ):
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 200)

    def test_kanban_drop_posts_transition(self):
        cand = self._candidate()
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.hr)
        resp = client.post(reverse('candidate_transition', args=[cand.pk]), {
            'to_status': Candidate.STATUS_REVIEWING, 'next': reverse('kanban_board'),
        })
        self.assertRedirects(resp, reverse('kanban_board'), fetch_redirect_response=False)
        cand.refresh_from_db()
        self.assertEqual(cand.status, Candidate.STATUS_REVIEWING)

    def test_dashboard_recruitment_tab_redirects(self):
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.hr)
        resp = client.get(reverse('admin_dashboard') + '?tab=recruitment')
        self.assertRedirects(resp, reverse('recruitment_overview'), fetch_redirect_response=False)


PDF_BYTES = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'


class CandidateFileTests(RecruitmentFlowBase):
    def setUp(self):
        super().setUp()
        import tempfile

        from django.test import override_settings

        self._media = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._media.name)
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        self._media.cleanup()
        super().tearDown()

    def _pdf(self, name='cv.pdf', content=PDF_BYTES):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(name, content, content_type='application/pdf')

    def test_files_stored_privately_and_served_with_permission(self):
        import os

        cand = self._candidate(files=[self._pdf()])
        f = cand.files.get()
        self.assertIn(os.path.join('_private', 'recruitment'), f.file.path)
        with self.assertRaises(ValueError):
            f.file.url  # không có link /media/ công khai
        url = reverse('recruitment_file', args=[f.pk])

        client = Client(HTTP_HOST='testserver')
        self.assertEqual(client.get(url).status_code, 302)  # chưa đăng nhập

        client.force_login(self.hr)
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('inline', resp['Content-Disposition'])
        self.assertEqual(resp['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(b''.join(resp.streaming_content), PDF_BYTES)
        self.assertIn('attachment', client.get(url + '?download=1')['Content-Disposition'])

        client.force_login(self.manager)
        self.assertEqual(client.get(url).status_code, 200)
        client.force_login(self.employee)
        self.assertEqual(client.get(url).status_code, 403)

    def test_interviewer_can_view_cv(self):
        cand = self._candidate(files=[self._pdf()])
        services.transition(cand, Candidate.STATUS_REVIEWING, actor=self.hr)
        services.submit_review(cand, self.manager, decision=CandidateReview.DECISION_RECOMMEND)
        services.transition(cand, Candidate.STATUS_INTERVIEWING, actor=self.hr,
                            interview_time=timezone.now(), interviewers=[self.employee])
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.employee)
        self.assertEqual(client.get(reverse('recruitment_file', args=[cand.files.get().pk])).status_code, 200)

    def test_rejects_wrong_type_and_fake_pdf(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        with self.assertRaises(services.RecruitmentError):
            self._candidate(files=[SimpleUploadedFile('cv.exe', b'MZ', content_type='application/octet-stream')])
        with self.assertRaises(services.RecruitmentError):
            self._candidate(files=[self._pdf(content=b'<html>not a pdf</html>')])
        self.assertFalse(Candidate.objects.exists())

    def test_upload_and_delete_from_detail(self):
        cand = self._candidate()
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.hr)
        resp = client.post(reverse('candidate_file_upload', args=[cand.pk]), {
            'kind': 'cv', 'files': [self._pdf('a.pdf'), self._pdf('b.pdf')],
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(cand.files.count(), 2)
        detail = client.get(reverse('candidate_detail', args=[cand.pk]))
        self.assertContains(detail, 'data-rc-cv')
        f = cand.files.first()
        path = f.file.path
        client.post(reverse('candidate_file_delete', args=[cand.pk, f.pk]))
        self.assertEqual(cand.files.count(), 1)
        import os

        self.assertFalse(os.path.exists(path))


class ManagerScopeTests(RecruitmentFlowBase):
    """TBP / TP / GĐ chỉ thấy ứng viên của vị trí mình quản lý."""

    def setUp(self):
        super().setUp()
        from hrm.models import Division
        from hrm.permissions import ROLE_DIVISION_HEAD

        self.div_a = Division.objects.create(name='Chuyền A RC', department=self.dept)
        self.div_b = Division.objects.create(name='Chuyền B RC', department=self.dept)
        self.tbp_a = _user('rc_tbp_a', role=ROLE_DIVISION_HEAD, department=self.dept)
        Profile.objects.filter(user=self.tbp_a).update(division=self.div_a)
        self.tbp_a.refresh_from_db()
        self.job_a = JobPosting.objects.create(
            title='May chuyền A', target_department=self.dept, target_division=self.div_a,
            position='Công nhân may', quantity=2, description='x',
            deadline=timezone.localdate() + timedelta(days=5), status=JobPosting.STATUS_OPEN,
        )
        self.job_b = JobPosting.objects.create(
            title='May chuyền B', target_department=self.dept, target_division=self.div_b,
            position='Công nhân may', quantity=2, description='x',
            deadline=timezone.localdate() + timedelta(days=5), status=JobPosting.STATUS_OPEN,
        )
        self.job_other = JobPosting.objects.create(
            title='Kế toán', target_department=self.other_dept, position='Kế toán', quantity=1,
            description='x', deadline=timezone.localdate() + timedelta(days=5), status=JobPosting.STATUS_OPEN,
        )
        mk = lambda job, name, phone: services.add_candidate(  # noqa: E731
            job, services.CandidateInput(full_name=name, phone=phone), actor=self.hr,
        )
        self.c_dept = mk(self.job, 'UV Phòng', '0911000001')
        self.c_a = mk(self.job_a, 'UV Chuyền A', '0911000002')
        self.c_b = mk(self.job_b, 'UV Chuyền B', '0911000003')
        self.c_other = mk(self.job_other, 'UV Kế toán', '0911000004')
        for c in (self.c_dept, self.c_a, self.c_b, self.c_other):
            services.transition(c, Candidate.STATUS_REVIEWING, actor=self.hr)

    def _visible(self, user):
        from recruitment.permissions import visible_jobs_q

        return set(Candidate.objects.filter(visible_jobs_q(user, 'job_posting__')).values_list('full_name', flat=True))

    def test_scopes(self):
        self.assertEqual(self._visible(self.tbp_a), {'UV Chuyền A'})
        self.assertEqual(self._visible(self.manager), {'UV Phòng', 'UV Chuyền A', 'UV Chuyền B'})
        self.assertEqual(self._visible(self.other_manager), {'UV Kế toán'})
        self.assertEqual(len(self._visible(self.director)), 4)  # GĐ không gắn phòng → toàn công ty
        self.assertEqual(len(self._visible(self.hr)), 4)  # quyền bổ sung «mọi phòng ban»
        self.assertEqual(self._visible(self.employee), set())

    def test_director_with_department_is_scoped(self):
        Profile.objects.filter(user=self.director).update(department=self.other_dept)
        self.director.refresh_from_db()
        self.assertEqual(self._visible(self.director), {'UV Kế toán'})

    def test_review_only_in_scope(self):
        services.submit_review(self.c_a, self.tbp_a, decision=CandidateReview.DECISION_RECOMMEND)
        with self.assertRaises(services.RecruitmentError):
            services.submit_review(self.c_b, self.tbp_a, decision=CandidateReview.DECISION_RECOMMEND)
        with self.assertRaises(services.RecruitmentError):
            services.submit_review(self.c_dept, self.tbp_a, decision=CandidateReview.DECISION_RECOMMEND)
        # HR thấy mọi phòng nhưng không đánh giá thay quản lý
        with self.assertRaises(services.RecruitmentError):
            services.submit_review(self.c_a, self.hr, decision=CandidateReview.DECISION_RECOMMEND)

    def test_hr_menu_pages_respect_scope(self):
        """Trưởng phòng có menu Tuyển dụng (không có quyền bổ sung) vẫn bị giới hạn."""
        group = _group('rc-tp-scoped', all_departments=False)
        Profile.objects.filter(user=self.other_manager).update(permission_group=group)
        self.other_manager.refresh_from_db()
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.other_manager)
        board = client.get(reverse('kanban_board'))
        self.assertContains(board, 'UV Kế toán')
        self.assertNotContains(board, 'UV Chuyền A')
        self.assertEqual(client.get(reverse('candidate_detail', args=[self.c_a.pk])).status_code, 404)
        self.assertEqual(client.get(reverse('job_posting_edit', args=[self.job_a.pk])).status_code, 404)
        resp = client.post(reverse('job_posting_create'), {
            'title': 'Ngoài phạm vi', 'target_department': self.dept.pk, 'position': 'Công nhân may',
            'quantity': 1, 'deadline': (timezone.localdate() + timedelta(days=3)).isoformat(), 'description': 'x',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(JobPosting.objects.filter(title='Ngoài phạm vi').exists())

    def test_review_list_shows_only_managed(self):
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.tbp_a)
        resp = client.get(reverse('recruitment_review_list'))
        self.assertContains(resp, 'UV Chuyền A')
        self.assertNotContains(resp, 'UV Chuyền B')
        self.assertNotContains(resp, 'UV Phòng')
        self.assertEqual(client.get(reverse('recruitment_review_candidate', args=[self.c_b.pk])).status_code, 403)
