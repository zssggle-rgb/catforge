import { DownloadOutlined } from "@ant-design/icons";
import { Button, Dropdown, message } from "antd";
import type { MenuProps } from "antd";
import type { Core3V2ExportItem } from "../../../types";

export function ReportExportActions({ exports }: { exports: Core3V2ExportItem[] }) {
  const items: MenuProps["items"] = exports.map((item) => ({
    key: item.export_type,
    label: item.export_title_cn
  }));
  return (
    <Dropdown
      menu={{
        items,
        onClick: ({ key }) => {
          const exportItem = exports.find((item) => item.export_type === key);
          if (!exportItem) {
            return;
          }
          navigator.clipboard
            ?.writeText(exportItem.export_payload)
            .then(() => message.success("报告内容已复制"))
            .catch(() => message.info("当前浏览器不支持自动复制，可在接口导出中获取报告内容"));
        }
      }}
      disabled={exports.length === 0}
    >
      <Button icon={<DownloadOutlined />}>导出报告</Button>
    </Dropdown>
  );
}

