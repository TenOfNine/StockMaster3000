import { Link } from "@tanstack/react-router";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/cn";

/** Verknüpft Journal-IDs (J-…) mit ihrer Trade-Akte. Kein Roh-HTML. */
function verlinken(text: string): string {
  return text.replace(/(?<![[\w/-])(J-\d{8}-\d{2})(?![\w\]])/g, "[$1](/entscheidungen/$1)");
}

export function Markdown({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn("prosa", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          a: ({ href, children }) =>
            href?.startsWith("/") ? (
              <Link to={href}>{children}</Link>
            ) : (
              <a href={href} target="_blank" rel="noreferrer noopener">
                {children}
              </a>
            ),
        }}
      >
        {verlinken(text)}
      </ReactMarkdown>
    </div>
  );
}
