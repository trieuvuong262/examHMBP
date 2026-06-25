/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { JustPlaySidebar } from "./justplay_sidebar";

const SIDEBAR_MEDIA = "(min-width: 992px)";

function isSidebarLayout() {
    return window.matchMedia(SIDEBAR_MEDIA).matches;
}

patch(NavBar, {
    components: { ...NavBar.components, JustPlaySidebar },
});

/**
 * Bỏ qua logic "More" khi dùng sidebar dọc tùy chỉnh.
 */
patch(NavBar.prototype, {
    async adapt() {
        if (!isSidebarLayout()) {
            return super.adapt(...arguments);
        }
        const sectionsMenu = this.appSubMenus.el;
        if (sectionsMenu) {
            for (const section of sectionsMenu.querySelectorAll(
                ":scope > *:not(.o_menu_sections_more)"
            )) {
                section.classList.remove("d-none");
            }
        }
        this.currentAppSectionsExtra = [];
    },
});
