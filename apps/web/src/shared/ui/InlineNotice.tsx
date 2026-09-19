import type { ReactNode } from "react";

interface InlineNoticeProps {
  children: ReactNode;
  tone: "error" | "success";
}

export function InlineNotice({ children, tone }: InlineNoticeProps) {
  return (
    <div className={`notice notice--${tone}`} role={tone === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}
