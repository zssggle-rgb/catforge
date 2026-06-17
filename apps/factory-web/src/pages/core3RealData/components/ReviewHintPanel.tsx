import { Alert } from "antd";
import type { Core3V2ReviewHint } from "../../../types";

export function ReviewHintPanel({ hint }: { hint?: Core3V2ReviewHint | null }) {
  if (!hint) {
    return null;
  }
  return (
    <Alert
      showIcon
      type={hint.review_required ? "warning" : "success"}
      title={hint.message_cn}
      description={hint.suggested_action_cn}
    />
  );
}
