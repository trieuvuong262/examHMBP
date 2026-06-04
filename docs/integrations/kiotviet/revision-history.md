# Revision History (tom tat tu paste)

`	ext
Revision History 
Ngày 	Version 	Nội dung thay đổi 
16/02/2017 	1.0 	Tạo phiên bản đầu tiên 
21/06/2017 	1.1 	Cập nhật: 
-	Mục 2. Chức năng, cập nhật “Authorization”: Bearer {Mã Access 
Token} trong header của các request. 
-	Mục 2.4.3. Thêm mới hàng hóa, trong Reqest: 
	•Xóa "fullName", "categoryName", "basePrice", "weight", 
"images" 
•Thêm "masterUnitId", "conversionValue" 
•Xóa  "productId",  "productCode", "productName" trong 
"inventories[]" 

Công ty CP phần mềm Citigo 	4/157 

 
 

 
Tài liệu hướng dẫn sử dụng Public API 	 Ver 4.0 

		-	Mục 2.4.4. Cập nhật hàng hóa, trong Request: 
	•Thêm "branchId", 
	•Xóa trường "fullName", "categoryName" 
	•Xóa  "productId",  "productCode", "productName" trong 
"inventories[]" 
-	Mục 2.5.3. Thêm mới đặt hàng, trong Request: 
	•Thêm "totalPayment", "accountId", "makeInvoice" 
	•Thêm "locationId", partnerDeliveryId" trong "orderDelivery[]" 	•Xóa "payments[]" 
-	Mục 2.5.4.Cập nhật đơn đặt hàng, trong Request: 	•Thêm "totalPayment", "accountId", "makeInvoice" 	•Xóa "payments[]" 
31/07/2017 	1.2 	Thêm: 
-	Thêm Mục 2.12 cung cấp các API cho hóa đơn. 
Cập nhật: 
-	Mục 2.5.1. Lấy danh sách đặt hàng: 
•Thêm tham số “customerCode", "toDate" 
•Thêm "customerCode”, “createdDate” trong response 
-	Mục 2.5.2. Lấy chi tiết đặt hàng: 
•Thêm “createdDate” trong response 
-	Mục 2.11.6. Đặt hàng và 2.11.7. Hóa đơn 
•Thêm “customerCode” 
06/04/2018 	1.3 	Thêm: 
-	Thêm Mục 2.13 cung cấp các API cho nhóm khách hàng. 
Cập nhật: 
-	Mục 2.6.1. Lấy danh sách khách hàng: 
•Thêm tham số “includeCustomerGroup " trong request 
•Thêm tham số “groups” trong response 
-	Mục 2.6.2. Lấy chi tiết khách hàng 
•Thêm tham số “groups” trong response 
-	Mục 2.6.3. Thêm mới khách hàng 
•Thêm tham số “groupIds” trong request 

Công ty CP phần mềm Citigo 	5/157 

 
 

 
Tài liệu hướng dẫn sử dụng Public API 	 Ver 4.0 

		•Thêm tham số “customerGroupDetails” trong response 
-	Mục 2.6.4. Cập nhật khách hàng 
•Thêm tham số “groupIds” trong request 
•Thêm tham số “groups” trong response 
18/04/2018 	1.4 	Cập nhật: 
-	Mục 2.4.2. Lấy chi tiết hàng hóa: 
•Thêm API lấy chi tiết theo Code 
•Thêm tham số “code” trong request 
-	Mục 2.5.2. Lấy chi tiết đặt hàng 
•Thêm API lấy chi tiết theo Code 
•Thêm tham số “code” trong request 
-	Mục 2.6.2. Lấy chi tiết khách hàng 
•Thêm API lấy chi tiết theo Code 
•Thêm tham số “code” trong request 
-	Mục 2.12.1. Lấy danh sách hóa đơn 
•Thêm tham số “orderId” trong request 
-	Mục 2.12.2. Lấy chi tiết hóa đơn 
•Thêm API lấy chi tiết theo Code 
•Thêm tham số “code” trong request 
16/07/2018 	1.5 	Thêm: 
-	Thêm mục 2.14 cung cấp các API cho sổ quỹ
•Thêm mục 2.14.1 : Lấy danh sách sổ quỹ
Cập nhật: 
-	Mục 2.6.4. Cập nhật khách hàng 
•Thêm tham số “taxCode” trong request 
-	Mục 2.5.1. Lấy danh sách đặt hàng 
•Thêm tham số “createdDate” trong request 
-	Mục 2.12.1. Lấy danh sách hóa đơn 
•Thêm tham số “createdDate” trong request 
-	Mục 2.4.1. Lấy danh hàng hóa 
•Thêm tham số “createdDate” trong response 
-	Mục 2.4.2. Lấy chi tiết hàng hóa 

Công ty CP phần mềm Citigo 	6/157 

 
 

 
Tài liệu hướng dẫn sử dụng Public API 	 Ver 4.0 

			•Thêm tham số “createdDate” trong response 
-	Mục 2.12.1, 2.12.2:  Lấy danh sách hóa đơn 
	•Thêm tham số “status”, “statusValue” trong “invoiceDelivery” 		(trạng thái vận đơn) 
-
	Mục 2.12.3, 2.12.4: Thêm mới, cập nhật hóa đơn 	•Thêm tham số “status” trong “deliveryDetail” (trạng thái vận 		đơn) 
-	Mục 2.11.7: Hóa đơn (Webhook) 
	•Thêm tham số “status”, “statusValue” trong “invoiceDelivery” 		(trạng thái vận đơn) 
30/07/2018 	1.6 	Thêm: 
-	Thêm mục 2.10.1: Thêm mới thu khác
-	Thêm mới 2.10.2: Cập nhật thu khác
-	Thêm mới 2.10.3: Ngừng hoạt động thu khác
Cập nhật: 
-	Mục 2.6.1. Lấy danh sách khách hàng; Mục 2.6.2. Lấy chi tiết khách 	hàng 
	•Thêm tham số “RewardPoint” trong response 
-	Mục 2.5.1. Lấy danh sách đặt hàng; Mục 2.5.2. Lấy chi tiết đặt 	hàng; Mục 2.12.1. Lấy danh sách hóa đơn; Mục 2.12.2. Lấy chi tiết 	hóa đơn
	•Thêm tham số “Note” trong response 
-	Mục 2.4.4. Cập nhật hàng hóa
	•Thêm tham số “IsActive” trong request
	•Thêm tham số “IsRewardPoint” trong request
-	Mục 2.5.3. Thêm mới đặt hàng; Mục 2.5.4. Cập nhật đặt hàng; 	Mục 2.12.3. Thêm mới hóa đơn
	•Thêm mới tham số “Surchages” trong request
-
	Mục 2.5.2. Lấy chi tiết đặt hàng; Mục 2.5.3. Thêm mới đặt hàng; 	Mục 2.5.4. Cập nhật đặt hàng
	•Thêm mới tham số “InvoiceOrderSurcharges” trong response
11/03/2019 	1.7 	Cập nhật: 

Công ty CP phần mềm Citigo 	7/157 

 
 

 
Tài liệu hướng dẫn sử dụng Public API 	 Ver 4.0 

		-	Mục 2.4.1 lấy danh sách hàng hóa 
•Thêm tham số “orderTemplate” trong response 
-	Mục 2.12.1 Lấy danh sách hóa đơn; Mục 2.12.2 Lấy chi tiết hóa đơn 
•Thêm tham số “SaleChannel” trong response 
-	Mục 2.6.1 Lấy danh sách khách hàng 
•Thêm tham số để lọc khách hàng theo ngày sinh nhật 
-	Mục 2.4 Cập nhật hàng hóa thêm tham số mới: 
•Thêm tham số “minQuantity” (định mức tồn nhỏ nhất) trong 
response 
•Thêm tham số “maxQuantity” (định mức tồn nhiều nhất) trong 
response 
Thêm: 
-	Mục 2.15 Phiếu nhập hàng: 
•Lấy danh sách phiếu nhập hàng 
•Lấy chi tiết phiếu nhập hàng 
-	Mục 2.4.6 Thêm API lấy thông tin thuộc tính sản phẩm 
25/07/2019 	1.8 	Cập nhật: 
-	Mục 2.4.1 Lấy danh sách hàng hóa 
	•Thêm tham số “productType” trong request. 	•Thêm tham số “includeMaterial” trong request. 	•Thêm tham số “productFormulas” trong response 
-	Mục 2.4.2 Lấy chi tiết hàng hóa 
	•Thêm tham số “productFormulas” trong response 
-	Mục 2.5.3 Thêm mới đặt hàng 
	•Thêm tham số “saleChannelId” trong request 	•Thêm tham số “saleChannelId” trong response 
-	Mục 2.5.4 Cập nhật đặt hàng 
	•Thêm tham số “saleChannelId” trong request 	•Thêm tham số “saleChannelId” trong response 
-	Mục 2.12.3 Thêm mới hóa đơn 
	•Thêm tham số “saleChannelId” trong request 	•Thêm tham số “saleChannelId” trong response 

Công ty CP phần mềm Citigo 	8/157 

 
 

 
Tài liệu hướng dẫn sử dụng Public API 	 Ver 4.0 

		-	Mục 2.12.4 Cập nhật hóa đơn 
•Thêm tham số “saleChannelId” trong request 
•Thêm tham số “saleChannelId” trong response 
Mục 2.15.1 Lấy danh sách nhập hàng, 2.15.2 Lấy chi tiết nhập hàng 
•Thêm tham số “supplierCode” trong response 
-	Mục 2.4.1 Lấy danh sách hàng hóa, 2.4.2 Lấy chi tiết hàng hóa: 
•Thêm tham số “isLotSerialControl” trong response 
•Thêm tham số “IsBatchExpireControl” trong response 
•Thêm tham số “productSerials” trong response 
•Thêm tham số “productBatchExpires” trong response 
-	Mục 2.12.1 Lấy danh sách hóa đơn, 2.12.2 Lấy chi tiết hóa đơn, 
2.15.1 Danh sách nhập hàng, 2.15.2 Chi tiết nhập hàng: 
•Thêm tham số “serialNumbers” trong response 
•Thêm tham số “productBatchExpire” trong response 
Thêm: 
-	Mục 2.16 Bảng giá: 
•Lấy danh sách bảng giá 
•Lấy chi tiết bảng giá 
-	Mục 2.17 Kênh bán hàng: 
•Lấy danh sách kênh bán hàng 
-	Mục 2.4.7 Thêm mới danh sách hàng hóa 
-	Mục 2.4.8  Cập nhật danh sách hàng hóa 
-	Mục 2.6.6 Thêm mới danh sách khách hàng 
-	Mục 2.6.7 Cập nhật danh sách khách hàng 
-	Mục 2.18 Trả hàng: 
•Thêm mục 2.18.1: Lấy danh sách phiếu trả hàng 
•Thêm mục 2.18.2: Lấy chi tiết phiếu trả hàng 
21/09/2019 	1.9 	Cập nhật: 
-	Mục 2.5.3 Thêm mới đặt hàng: 
•Thêm tham số “ExpectedDelivery” trong Request 
-	Mục 2.2.4 Cập nhật đặt hàng: 

Công ty CP phần mềm Citigo 	9/157 

 
 

 
Tài liệu hướng dẫn sử dụng Public API 	 Ver 4.0 

		•Thêm tham số “ExpectedDelivery” trong Request 
-	Mục 2.12.1 Lấy danh sách hóa đơn 
•Thêm tham số “FromPurchaseDate” và “ToPurchaDate” trong 
Request 
-	Mục 2.12.2  Lấy chi tiết hóa đơn 
•Thêm tham số “OrderCode” trong Response 
-	Mục 2.12.3  Thêm mới hóa đơn 
•Thêm tham số “ExpectedDelivery” trong Request 
-	Mục 2.4.1 Lấy danh sách hàng hóa 
•Thêm tham số “MasterProductId” trong Request 
-	Mục 2.12.4 Cập nhật hóa đơn 
•Thêm tham số “ExpectedDelivery” trong Request 
-	Mục 2.5.3 Thêm mới đặt hàng: 
•Thêm tham số “Note” trong Request 
-	Mục 2.12.3  Thêm mới hóa đơn 
•Thêm tham số “Note” trong Request 
-	Mục 2.4.2. Lấy chi tiết hàng hóa 
•Thêm tham số “type” trong response 
-	Mục 2.5.3. Thêm mới đặt hàng 
•Thêm tham số “partner” trong request header 
Thêm: 
-	Mục 2.19 Đặt hàng nhập: 
•Lấy danh sách Đặt hàng nhập 
•Lấy chi tiết Đặt hàng nhập 
-	Mục 2.2 Danh sách location: 
•Lấy danh sách location 
-	Thêm mục 2.21 cung cấp các API cho thiết lập cửa hàng 
-	Mục 2.6.3 Thêm mới khách hàng 
•Thêm tham số “type” trong response 

Công ty CP phần mềm Citigo 	10/157 

 
 

 
Tài liệu hướng dẫn sử dụng Public API 	 Ver 4.0 

30/10/2019 	2.0 	Cập nhật: 
-	Mục 2.6.1 Lấy danh sách khách hàng 
•Thêm tham số và trả về thông tin Psid facebook fanpage của 
khách hàng 
-	Mục 2.6.2 Lấy chi tiết khách hàng 
•Trả về thông tin Psid facebook fanpage của khách hàng 

14/10/2020 	2.1 	Cập nhật lại URL : https://public.kiotapi.com/surchages
12/01/2021 	2.1.1 	Mục 2.5 và 2.6 sửa lại tên biến “comment” => “comments” cho đối tượng khách hàng 
20/01/2021 	2.1.2 	Bổ sung thêm trường “barCode” trong API Lấy danh sách hàng hóa, lấy chi tiết hàng hóa, thêm mới/cập nhật hàng hóa. 
04/06/2021 	2.2 	Bổ sung thêm : 
2.15.3. Thêm mới nhập hàng 
2.15.4. Cập nhật nhập hàng 
2.15.5. Xóa nhập hàng 
17/6 	2.2.1 	Sửa 1 số lỗi sai  và bỏ thông tin thừa 
“barCode”: string, // Mã vạch hàng hóa (Tối đa 16 ký tự) trang 23, 27, 32, 33, 35, 36 
“usingCod”” bool, // Có tạo phiếu giao hàng không? trang 50, trang 55 - “usingPriceCod”: bool,/ Có thu hộ hay không? Trang 51, trang 56 - “description”: string, / Trang 97, 102 
- “status”: byte, (1: Chờ xử lý, 2: Đang giao hàng) //trạng thái vận đơn trang 98, 100 
- “status”: byte, (1: Chờ xử lý, 2: Đang giao hàng,3: Giao thành công, 4:Đang chuyển hoàn, 5:Đã chuyển hoàn, 6:Đã hủy, 7: Đang lấy hàng, 8:Chờ lấy lại, 9:Đã lấy hàng, 10:Chờ giao lại, 11:Chờ chuyển hàng, 12:Chờ chuyển hoàn lại) //trạng thái vận đơn trang 103, 105 

Công ty CP phần mềm Citigo 	11/157 

 
 

 
Tài liệu hướng dẫn sử dụng Public API 	 Ver 4.0 

		- “includeInvoiceDelivery”: Boolean, //hóa đơn có giao hàng hay không trang 88 
- “branchId”: int,            // Id chi nhánh (Không cập nhật trường này) trang 118 
- "serialNumbers": string, // Danh sách imei 
	 "productBatchExpire": { 
		 "id": long,             // Id lô 
		 "productId": long,       // ID sản phẩm 
		 "batchName": string,    // Tên 
		 "fullNameVirgule": string, // Tên đầy đủ 
		 "createdDate": DateTime, // Ngày tạo lô 
		 "expireDate": DateTime  // Ngày hết hạn lô 
		 } 
Tạo phiếu nhập chưa hỗ trợ hàng hóa IMEI, lô date, thông tin respone dư trang 117, 120 
- Thay đổi 
https://public.kiotapi.com/purchaseorders?id={Id}?IsVoidPayment=true thành 
https://public.kiotapi.com/purchaseorders?id={Id}&IsVoidPayment=true trang 121 
23/6 	2.2.2 	Hoàn thiện nốt ver 2.2.1 
Bổ sung : 
Mục 1 : lưu ý về các trường không bắt buộc 
26/08/21 	2.2.3 	•Bổ sung : 
2.4.1 Lấy danh sách hàng hóa : thêm mục get thông tin bảo hành bảo trì 
2.12.3 và 2.12.4 : thêm mô tả cho trường wardName 
04/10/2021 	3.0 	•Bổ sung 2.16 – Chuyển hàng 

Công ty CP phần mềm Citigo 	12/157 

 
 

 
Tài liệu hướng dẫn sử dụng Public API 	 Ver 4.0 

		•2.5.3 và 2.5.4 thêm wardName 
18/10/2021 	3.1 	•Bổ sung : 2.16.4 Cập nhật chuyển hàng 
28/10/2021 	3.2 	2.12.3 Thêm mới hóa đơn 
•Bổ sung thông tin Serial/Imei khi tạo hóa đơn 
02/03/2022 	3.3 	•2.4.9 Lấy danh sách tồn kho hàng hóa 
•2.12.3 Thêm mới hóa đơn 
Thêm hàm tạo mới Khách hàng 
23/03/2022 	3.4 	•	Thêm "includeSoftDeletedAttribute" 
Lấy danh sách hàng hóa 
Lấy chi tiết hàng hóa 
•	Cập nhật thêm các tham số trong danh sách hàng hóa 
31/03/2022 	3.5 	•	Thêm phương thức thanh toán voucher khi Đặt hàng 
2.5.3 Thêm mới đặt hàng 
•	Bổ sung thêm trường Serial/Imei trong mục 
 2.4.3 Thêm mới hàng hóa 
21/06/2022 	3.6 	•	Bổ sung branchID trong : 2.6.3 
•	Sửa lại link lấy danh sách tồn kho hàng hóa: 2.4.9 
•	Cập nhật trạng thái vận đơn trong thêm mới/cập nhật hóa 
đơn: 2.12.3, 2.12.4 
05/07/2022 	3.7 	2.16.1 Lấy danh sách chuyển hàng 
Bổ sung: 
“currentItem”: int?, // Lấy dữ liệu từ bản ghi currentItem,  “fromReceivedDate”: DateTime?, // Từ thời gian nhận chuyển hàng, 
 “toReceivedDate”: DateTime?, // Đến thời gian nhận chuyển hàng, 
 “fromTransferDate”: DateTime?, // Từ thời gian chuyển hàng, 

Công ty CP phần mềm Citigo 	13/157 

 
 

 
Tài liệu hướng dẫn sử dụng Public API 	 Ver 4.0 

		 “toTransferDate”: DateTime?, // Đến thời gian chuyển hàng, 	
21/12/2022 	3.8 		2. Chức năng 
 Bổ sung:  
Lưu ý: Với các hàm GET sẽ giới hạn 5000 request/1h 2.4.1 Lấy danh sách hàng hóa 
- bổ sung: includeWarranties - Lấy thông tin bảo hành -  bỏ: "status": int, // 0: Lô tạm, 1: lô hoàn thành 2.4.2 Lấy chi tiết hàng hóa 
- bỏ: "status": int, // 0: Lô tạm, 1: lô hoàn thành 	
				
17/01/2023 	4.0 	Bổ sung thêm: 
2.17.3. Cập nhật chi tiết bảng giá 	

Công ty CP phần mềm Citigo 	14/157 

 
 

 
Tài liệu hướng dẫn sử dụng Public API 	 Ver 4.0
`
