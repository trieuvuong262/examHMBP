import io
from datetime import datetime

import pandas as pd
from django.http import HttpResponse


def dataframe_to_xlsx_response(df: pd.DataFrame, filename_prefix: str, sheet_name: str = 'Bao_cao') -> HttpResponse:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    stamp = datetime.now().strftime('%Y%m%d_%H%M')
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename={filename_prefix}_{stamp}.xlsx'
    return response
