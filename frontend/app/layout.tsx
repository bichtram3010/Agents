import "./globals.css";
import "@copilotkit/react-ui/styles.css";
import type { Metadata } from "next";
import { CopilotKit } from "@copilotkit/react-core";

export const metadata: Metadata = {
  title: "Odoo Multi-Agent | Fashion & Cosmetics",
  description: "Trợ lý đa agent quản lý shop thời trang & mỹ phẩm trên Odoo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="min-h-screen bg-neutral-50 text-neutral-900">
        <CopilotKit runtimeUrl="/api/copilotkit" showDevConsole={false}>
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}
