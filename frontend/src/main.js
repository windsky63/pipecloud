import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import InfoTooltip from './components/InfoTooltip.vue'
import { i18n } from './i18n'
import { vuetify } from './plugins/vuetify'
import router from './router'

// 应用入口只负责组装插件；各插件的具体配置位于对应目录。
createApp(App).component('InfoTooltip', InfoTooltip).use(i18n).use(vuetify).use(router).mount('#app')
