from django import forms

from .models import Survey, SurveyResponse


MAX_SURVEY_QUESTIONS = 30
MAX_OPTIONS_PER_QUESTION = 20
MAX_QUESTION_LENGTH = 2000


class SurveyCreateForm(forms.ModelForm):
    class Meta:
        model = Survey
        fields = ('title', 'reference_url', 'required_course', 'deadline', 'is_active')
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: Định hướng làm việc tại xưởng mới',
            }),
            'reference_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://... (tuỳ chọn)',
            }),
            'required_course': forms.Select(attrs={'class': 'form-select'}),
            'deadline': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={
                    'class': 'form-control',
                    'type': 'datetime-local',
                },
            ),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'title': 'Tiêu đề',
            'reference_url': 'Link tham khảo',
            'required_course': 'Bài học gợi ý (tuỳ chọn)',
            'deadline': 'Hạn nhận câu hỏi',
            'is_active': 'Đang mở nhận phản hồi',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deadline'].required = False
        self.fields['reference_url'].required = False
        self.fields['required_course'].required = False
        self.fields['deadline'].input_formats = [
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
        ]
        self.fields['required_course'].queryset = (
            self.fields['required_course'].queryset.filter(is_active=True).order_by('title')
        )
        self.fields['required_course'].empty_label = '— Không bắt buộc học trước —'


class SurveyReferenceForm(forms.ModelForm):
    class Meta:
        model = Survey
        fields = ('reference_url', 'required_course')
        widgets = {
            'reference_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://...',
            }),
            'required_course': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'reference_url': 'Link tham khảo / tài liệu',
            'required_course': 'Bài học gợi ý (tuỳ chọn)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['required_course'].required = False
        self.fields['required_course'].queryset = (
            self.fields['required_course'].queryset.filter(is_active=True).order_by('title')
        )
        self.fields['required_course'].empty_label = '— Không bắt buộc học trước —'


class SurveyResponseForm(forms.ModelForm):
    class Meta:
        model = SurveyResponse
        fields = ('answer',)
        widgets = {
            'answer': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Anh/chị vui lòng cân nhắc, đọc kỹ Sổ tay nhân viên và các văn bản quy định trước khi đặt câu hỏi. Nếu nội dung chưa rõ hoặc cần giải thích thêm, vui lòng ghi cụ thể nội dung cần được giải đáp',
            }),
        }
        labels = {
            'answer': 'Nhập câu hỏi',
        }


def parse_survey_question_payload(post):
    """Đọc các câu hỏi trắc nghiệm từ form tạo khảo sát.

    Mỗi câu có nội dung, cờ bắt buộc và danh sách đáp án.
    Trả về (danh sách câu, danh sách lỗi).
    """
    try:
        count = int(post.get('q_count') or 0)
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        count = 0
        while f'q_{count}_content' in post and count < MAX_SURVEY_QUESTIONS:
            count += 1
    count = max(0, min(count, MAX_SURVEY_QUESTIONS))

    blocks = []
    for index in range(count):
        content = (post.get(f'q_{index}_content') or '').strip()[:MAX_QUESTION_LENGTH]
        is_required = (post.get(f'q_{index}_required') or '0') == '1'
        options = []
        for opt_index in range(MAX_OPTIONS_PER_QUESTION):
            key = f'q_{index}_opt_{opt_index}'
            if key not in post:
                break
            options.append((post.get(key) or '').strip()[:500])
        if not content and not any(options):
            continue
        blocks.append({
            'content': content,
            'is_required': is_required,
            'options': options,
        })

    if not blocks:
        return [{'content': '', 'is_required': True, 'options': ['', '']}], [
            'Cần ít nhất một câu hỏi, mỗi câu có từ 2 đáp án.',
        ]

    errors = []
    for number, block in enumerate(blocks, start=1):
        filled = [label for label in block['options'] if label]
        if not block['content']:
            errors.append(f'Câu {number}: chưa nhập nội dung câu hỏi.')
        if len(filled) < 2:
            errors.append(f'Câu {number}: cần ít nhất 2 đáp án.')
        seen = set()
        for label in filled:
            key = label.casefold()
            if key in seen:
                errors.append(f'Câu {number}: đáp án «{label}» bị trùng.')
                break
            seen.add(key)
        block['options_to_save'] = filled
    return blocks, errors


def format_survey_answers(pairs):
    lines = []
    for index, (question, option) in enumerate(pairs, start=1):
        lines.append(f'{index}. {question.content}')
        lines.append(f'→ {option.label if option else "—"}')
    return '\n'.join(lines)
