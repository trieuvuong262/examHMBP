/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { CheckBox } from "@web/core/checkbox/checkbox";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { imageUrl } from "@web/core/utils/urls";

const userMenuRegistry = registry.category("user_menuitems");

/** Icon đơn sắc (Font Awesome) — không dùng webIconData màu của Odoo */
const APP_ICON_BY_XMLID = {
    "mail.menu_root_discuss": "fa-comment-o",
    "spreadsheet_dashboard.spreadsheet_dashboard_menu_root": "fa-bar-chart",
    "stock.menu_stock_root": "fa-cubes",
    "mrp.menu_mrp_root": "fa-industry",
    "maintenance.menu_maintenance_title": "fa-wrench",
    "maintenance.menu_maintenance_title_root": "fa-wrench",
    "purchase.menu_purchase_root": "fa-shopping-cart",
    "account.menu_finance": "fa-calculator",
    "sale.sale_menu_root": "fa-shopping-bag",
    "base.menu_management": "fa-th-large",
    "hr.menu_hr_root": "fa-users",
};

const APP_ICON_BY_NAME = [
    ["thảo luận", "fa-comment-o"],
    ["báo cáo", "fa-bar-chart"],
    ["tồn kho", "fa-cubes"],
    ["sản xuất", "fa-industry"],
    ["bảo dưỡng", "fa-wrench"],
    ["bảo trì", "fa-wrench"],
    ["mua hàng", "fa-shopping-cart"],
    ["kế toán", "fa-calculator"],
    ["bán hàng", "fa-shopping-bag"],
    ["ứng dụng", "fa-th-large"],
    ["nhân sự", "fa-users"],
];

export function getAppIconClass(app) {
    if (app?.xmlid && APP_ICON_BY_XMLID[app.xmlid]) {
        return APP_ICON_BY_XMLID[app.xmlid];
    }
    const name = (app?.name || "").toLowerCase();
    for (const [keyword, icon] of APP_ICON_BY_NAME) {
        if (name.includes(keyword)) {
            return icon;
        }
    }
    return "fa-folder-o";
}

export class JustPlayProfileCard extends Component {
    static template = "portal_justplay_brand.JustPlayProfileCard";
    static components = { Dropdown, DropdownItem, CheckBox };
    static props = {};

    setup() {
        this.userName = user.name;
        this.userLogin = user.login;
        this.roleLabel = user.isAdmin || user.isSystem ? "Quản trị" : "Nhân viên";
        this.avatarUrl = imageUrl("res.partner", user.partnerId, "avatar_128", {
            unique: user.writeDate,
        });
        this.state = useState({ avatarError: false, department: "" });
        this.orm = useService("orm");

        onWillStart(async () => {
            try {
                const employees = await this.orm.searchRead(
                    "hr.employee",
                    [["user_id", "=", user.userId]],
                    ["department_id"],
                    { limit: 1 }
                );
                const dept = employees[0]?.department_id;
                if (Array.isArray(dept) && dept[1]) {
                    this.state.department = dept[1];
                }
            } catch {
                // hr chưa cài hoặc không có employee
            }
        });
    }

    get userInitial() {
        const n = (this.userName || this.userLogin || "?").trim();
        return n.charAt(0).toUpperCase();
    }

    onAvatarError() {
        this.state.avatarError = true;
    }

    getElements() {
        return userMenuRegistry
            .getAll()
            .map((element) => element(this.env))
            .filter((element) => (element.show ? element.show() : true))
            .sort((x, y) => (x.sequence || 100) - (y.sequence || 100));
    }
}
