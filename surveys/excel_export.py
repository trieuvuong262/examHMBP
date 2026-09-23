import io
from collections import defaultdict
from datetime import datetime

import pandas as pd
from django.http import HttpResponse
from django.utils import timezone
from openpyxl.styles import Font

from .forms import QUESTION_TYPE_TEXT
from .models import SurveyAnswer


def export_survey_result_xlsx(survey) -> HttpResponse:
    questions = list(survey.questions.prefetch_related('options'))
    rows = _detail_rows(survey, questions)
    if not rows:
        rows = [{
            'STT câu': '',
            'Câu hỏi': '',
            'Đáp án': '',
            'Số người chọn': 0,
            'Mã NV': '',
            'Họ và tên': '',
            'Bộ phận': '',
            'Thời gian gửi': '',
        }]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        frame = pd.DataFrame(rows)
        frame.to_excel(writer, index=False, sheet_name='Chi tiết')
        sheet = writer.sheets['Chi tiết']
        widths = {
            'A': 10,
            'B': 48,
            'C': 42,
            'D': 16,
            'E': 14,
            'F': 28,
            'G': 24,
            'H': 20,
        }
        for column, width in widths.items():
            sheet.column_dimensions[column].width = width
        for cell in sheet[1]:
            cell.font = Font(bold=True)

    stamp = datetime.now().strftime('%Y%m%d_%H%M')
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename=khao-sat-{survey.pk}_{stamp}.xlsx'
    return response


def _detail_rows(survey, questions):
    if not questions:
        return _legacy_rows(survey)

    answers = SurveyAnswer.objects.filter(response__survey=survey).select_related(
        'response', 'question', 'option',
    )
    people_by_option = defaultdict(list)
    people_by_text_question = defaultdict(list)
    for answer in answers:
        person = _person(answer.response)
        if answer.question.q_type == QUESTION_TYPE_TEXT:
            person['answer_text'] = (answer.text_value or '').strip()
            if person['answer_text']:
                people_by_text_question[answer.question_id].append(person)
        elif answer.option_id:
            people_by_option[answer.option_id].append(person)

    rows = []
    for index, question in enumerate(questions, start=1):
        if question.q_type == QUESTION_TYPE_TEXT:
            people = sorted(
                people_by_text_question.get(question.pk, []),
                key=_person_sort,
            )
            if not people:
                rows.append(_blank_row(index, question.content, '', 0))
                continue
            for person in people:
                rows.append(_filled_row(
                    index,
                    question.content,
                    person['answer_text'],
                    len(people),
                    person,
                ))
            continue

        options = list(question.options.all())
        if not options:
            rows.append(_blank_row(index, question.content, '', 0))
            continue
        for option in options:
            people = sorted(people_by_option.get(option.pk, []), key=_person_sort)
            if not people:
                rows.append(_blank_row(index, question.content, option.label, 0))
                continue
            for person in people:
                rows.append(_filled_row(
                    index,
                    question.content,
                    option.label,
                    len(people),
                    person,
                ))
    return rows


def _legacy_rows(survey):
    rows = []
    responses = survey.responses.all().order_by('full_name', 'employee_code')
    total = responses.count()
    question = (survey.question or '').strip()
    for response in responses:
        text = (response.answer or '').strip()
        if not text:
            continue
        rows.append(_filled_row(1, question, text, total, _person(response)))
    return rows


def _person(response):
    submitted = response.submitted_at
    if submitted:
        submitted = timezone.localtime(submitted).strftime('%d/%m/%Y %H:%M')
    else:
        submitted = ''
    return {
        'employee_code': response.employee_code or '',
        'full_name': response.full_name or '',
        'department_name': response.department_name or '',
        'submitted_at': submitted,
    }


def _person_sort(person):
    return (
        (person.get('full_name') or '').casefold(),
        (person.get('employee_code') or '').casefold(),
    )


def _blank_row(index, question, answer, total):
    return {
        'STT câu': index,
        'Câu hỏi': question,
        'Đáp án': answer,
        'Số người chọn': total,
        'Mã NV': '',
        'Họ và tên': '',
        'Bộ phận': '',
        'Thời gian gửi': '',
    }


def _filled_row(index, question, answer, total, person):
    row = _blank_row(index, question, answer, total)
    row['Mã NV'] = person['employee_code']
    row['Họ và tên'] = person['full_name']
    row['Bộ phận'] = person['department_name']
    row['Thời gian gửi'] = person['submitted_at']
    return row
