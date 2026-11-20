/**
 * Thẻ trạng thái trong khung chat khi CopilotKit chạy một action (ask_agent,
 * create_order...): người dùng thấy đang làm gì thay vì chỉ "• • •".
 */
export default function ToolStatus({ done, running, finished }: {
  done: boolean;
  running: string;
  finished: string;
}) {
  return (
    <div className={`ck-tool ${done ? "ck-tool-done" : ""}`}>
      {done ? <span aria-hidden>✓</span> : <span className="ck-spinner" aria-hidden />}
      <span>{done ? finished : running}</span>
    </div>
  );
}
