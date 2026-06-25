/** @odoo-module **/

import { Component, useState, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { JustPlayProfileCard, getAppIconClass } from "./justplay_profile";

export class JustPlaySidebar extends Component {
    static template = "portal_justplay_brand.JustPlaySidebar";
    static components = { JustPlayProfileCard };
    static props = {};

    setup() {
        this.menuService = useService("menu");
        this.getAppIconClass = getAppIconClass;
        this.state = useState({
            openAppIds: {},
            openMenuIds: {},
        });

        const syncCurrentApp = () => {
            const app = this.menuService.getCurrentApp();
            if (app) {
                this.state.openAppIds = { ...this.state.openAppIds, [app.id]: true };
            }
        };

        syncCurrentApp();
        this.env.bus.addEventListener("MENUS:APP-CHANGED", syncCurrentApp);
        onWillUnmount(() => {
            this.env.bus.removeEventListener("MENUS:APP-CHANGED", syncCurrentApp);
        });
    }

    get apps() {
        return this.menuService.getApps();
    }

    isAppOpen(app) {
        return Boolean(this.state.openAppIds[app.id]);
    }

    isAppActive(app) {
        return this.menuService.getCurrentApp()?.id === app.id;
    }

    getAppSections(app) {
        return this.menuService.getMenuAsTree(app.id).childrenTree || [];
    }

    async toggleApp(app) {
        const willOpen = !this.state.openAppIds[app.id];
        this.state.openAppIds = { ...this.state.openAppIds, [app.id]: willOpen };
        if (willOpen && app.actionID) {
            await this.menuService.selectMenu(app);
        }
    }

    isNestedOpen(item) {
        return Boolean(this.state.openMenuIds[item.id]);
    }

    toggleNested(item, ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const willOpen = !this.state.openMenuIds[item.id];
        this.state.openMenuIds = { ...this.state.openMenuIds, [item.id]: willOpen };
    }

    async onMenuClick(menu, ev) {
        ev.preventDefault();
        await this.menuService.selectMenu(menu);
        if (menu.appID) {
            this.state.openAppIds = { ...this.state.openAppIds, [menu.appID]: true };
        }
    }

    getMenuHref(menu) {
        if (!menu.actionID) {
            return "#";
        }
        return menu.actionPath ? `/odoo/${menu.actionPath}` : `/odoo/action-${menu.actionID}`;
    }
}
