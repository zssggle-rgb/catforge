import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import "./styles.css";

export default function FactoryRoot() {
  return <ConfigProvider locale={zhCN}><App /></ConfigProvider>;
}
