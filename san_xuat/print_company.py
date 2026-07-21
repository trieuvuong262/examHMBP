"""Thông tin công ty in trên phiếu sản xuất (A5)."""

COMPANY_TAX_CODE = '0316184836'
COMPANY_NAME = 'CÔNG TY TNHH JUST PLAY'
COMPANY_ADDRESS = '19 Chiến Lược, Bình Trị Đông, Bình Tân, TP. Hồ Chí Minh'

# Vai trò ký theo loại phiếu (nhãn hiển thị trên giấy)
SIGNATURES = {
    'mo': (
        'Người lập',
        'Tổ trưởng',
        'Điều phối SX',
        'Phụ trách xưởng',
    ),
    'ycx': (
        'Người yêu cầu',
        'Thủ kho NPL',
        'Người nhận',
        'Điều phối SX',
    ),
    'qc': (
        'Người kiểm',
        'Tổ trưởng',
        'Phụ trách QC',
        'Điều phối SX',
    ),
    'packing': (
        'Người đóng gói',
        'Thủ kho TP',
        'Điều phối SX',
        'Xác nhận',
    ),
    'ycntp': (
        'Người yêu cầu',
        'Thủ kho TP',
        'Điều phối SX',
        'Xác nhận',
    ),
    'handover': (
        'Bên giao',
        'Bên nhận',
        'Tổ trưởng',
        'Điều phối SX',
    ),
    'subcontract': (
        'Người lập',
        'Đơn vị GC',
        'Thủ kho',
        'Điều phối SX',
    ),
    'ncr': (
        'Người lập',
        'Phụ trách QC',
        'Điều phối SX',
        'Phụ trách xưởng',
    ),
    'qc_alert': (
        'Người ghi nhận',
        'Phụ trách QC',
        'Tổ trưởng',
        'Điều phối SX',
    ),
}
