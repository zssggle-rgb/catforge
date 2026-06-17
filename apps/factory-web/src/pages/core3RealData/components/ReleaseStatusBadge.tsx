import { Tag } from "antd";
import type { Core3V2ReleaseStatus } from "../../../types";
import { releaseStatusColor, releaseStatusLabel } from "../core3RealDataFormat";

export function ReleaseStatusBadge({ status }: { status?: Core3V2ReleaseStatus | null }) {
  return <Tag color={releaseStatusColor(status?.status_code)}>{releaseStatusLabel(status)}</Tag>;
}

