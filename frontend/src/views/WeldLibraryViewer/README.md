# WeldLibraryViewer

焊口库与相关库维护页面，对应路由 `/libraries/:libraryKey`。

## 页面职责

- 按库类型加载 Excel 工作表数据，并使用 VTable 展示与编辑。
- 支持工作表切换、列显示控制、批量编辑、撤销和保存。
- 在存在未保存修改时提供离开确认。

## 文件结构

- `index.vue`: 页面入口，维护库路由、VTable 生命周期、编辑历史、批量操作和保存逻辑。
- `WeldLibraryHeader.vue`: 页面标题区局部组件，封装当前页面对公共 `PageHeader` 的使用。
