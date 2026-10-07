import { Link } from "@tanstack/react-router";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/cn";

import { Fehlergrenze } from "./Fehlergrenze";

const AKTE = /^\/entscheidungen\/J-\d{8}-\d{2}$/;

/** Verknüpft Journal-IDs (J-…) mit ihrer Trade-Akte. Kein Roh-HTML. */
function verlinken(text: string): string {
  return text.replace(
    /(?<![[\w/-])(J-\d{8}-\d{2})(?![\w\]])/g,
    "[$1](/entscheidungen/$1)",
  );
}

export function Markdown({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  return (
    <div className={cn("prosa", className)}>
      <Fehlergrenze
        ersatz={() => (
          <pre className="font-mono text-[12.5px] whitespace-pre-wrap text-text-2">
            {text}
          </pre>
        )}
      >
        <MarkdownInhalt text={text} />
      </Fehlergrenze>
    </div>
  );
}

function MarkdownInhalt({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeSanitize]}
      components={{
        // Nur Trade-Akten sind interne Ziele; alles andere öffnet extern oder bleibt Text.
        a: ({ href, children }) =>
          href && AKTE.test(href) ? (
            <Link to="/entscheidungen/$id" params={{ id: href.split("/")[2] }}>
              {children}
            </Link>
          ) : href && /^(https?:|mailto:)/i.test(href) ? (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ) : (
            <span>{children}</span>
          ),
      }}
    >
      {verlinken(text)}
    </ReactMarkdown>
  );
}
