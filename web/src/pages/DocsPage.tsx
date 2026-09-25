import { useLayoutEffect } from "react";
import { ExternalLink } from "lucide-react";
import { useI18n } from "@/i18n";
import { usePageHeader } from "@/contexts/usePageHeader";
import { cn } from "@/lib/utils";
import { PluginSlot } from "@/plugins";

// Docs are served from GitHub, which refuses to be framed, so this page links
// out instead of embedding the docs site in an iframe.
export const ANTHOS_DOCS_URL =
  "https://github.com/TushaeBXN/anthos-agent/tree/main/website/docs";

const DS_BUTTON_OUTLINED_LINK_CN = cn(
  "group relative inline-grid grid-cols-[auto_1fr_auto] items-center",
  "px-[.9em_.75em] py-[1.25em] gap-2",
  "leading-0 font-bold tracking-[0.2em] uppercase",
  "text-midground bg-transparent shadow-midground",
  "shadow-[inset_-1px_-1px_0_0_#00000080,inset_1px_1px_0_0_#ffffff80]",
);

export default function DocsPage() {
  const { t } = useI18n();
  const { setEnd } = usePageHeader();

  useLayoutEffect(() => {
    setEnd(
      <a
        href={ANTHOS_DOCS_URL}
        target="_blank"
        rel="noopener noreferrer"
        className={DS_BUTTON_OUTLINED_LINK_CN}
      >
        <ExternalLink className="size-3.5" />
        {t.app.openDocumentation}
      </a>,
    );
    return () => {
      setEnd(null);
    };
  }, [setEnd, t]);

  return (
    <div
      className={cn(
        "flex min-h-0 w-full min-w-0 flex-1 flex-col",
        "pt-1 sm:pt-2",
      )}
    >
      <PluginSlot name="docs:top" />
      <div
        className={cn(
          "flex min-h-0 w-full min-w-0 flex-1 flex-col items-center justify-center gap-4",
          "rounded-sm border border-current/20 p-6 text-center",
        )}
      >
        <p className="font-bold tracking-[0.2em] uppercase">
          {t.app.nav.documentation}
        </p>
        <a
          href={ANTHOS_DOCS_URL}
          target="_blank"
          rel="noopener noreferrer"
          className={DS_BUTTON_OUTLINED_LINK_CN}
        >
          <ExternalLink className="size-3.5" />
          {t.app.openDocumentation}
        </a>
      </div>
      <PluginSlot name="docs:bottom" />
    </div>
  );
}
