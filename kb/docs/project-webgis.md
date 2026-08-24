# 实习：中地数码科技有限公司（前端开发，WebGIS 方向）

> 技术栈：Vue3 / ArcGIS API for JavaScript

## 地图渲染

基于 Vue3 + ArcGIS API for JavaScript 搭建地图前端页面，完成基础地图底图加载、图层切换与视口控制功能。

## 数据可视化

调用 ArcGIS FeatureLayer 和 GraphicsLayer 接口，实现城市交通流量、实时天气、区域人流热力等多维度数据的点位渲染与专题图展示。

## 查询交互

设计空间查询与属性筛选面板，支持按区域、时间、类型多条件组合过滤地图要素，查询结果高亮显示并联动信息弹窗。

## 接口联调

封装 Axios 请求模块，对接后端 RESTful 数据接口，处理 GeoJSON 格式数据的解析与图层更新逻辑。

## 性能优化

针对大规模点位数据（万级）渲染卡顿问题，采用 ArcGIS 客户端聚合（Cluster）与按需加载策略。
