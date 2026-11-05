import { X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { PlayerSheetBody } from "./PlayerSheetBody";

type Props = { gsisId: string; name: string; position: string; season: number; text?: string };

/** The name as a button (styled as a link) that opens a Radix Dialog sheet: bottom on phones, right side from md up. */
export function PlayerSheet({ gsisId, name, position, season, text }: Props) {
  const [open, setOpen] = useState(false);
  const { pathname, search } = useLocation();
  // A close caused by navigation must not pull focus back to a name that may be gone.
  const closedByNavigation = useRef(false);
  useEffect(() => {
    closedByNavigation.current = true;
    setOpen(false);
  }, [pathname, search]);
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (next) closedByNavigation.current = false;
        setOpen(next);
      }}
    >
      <Dialog.Trigger className="inline-flex min-h-[44px] items-center text-left underline decoration-border underline-offset-4 hover:decoration-text lg:min-h-0">
        <span>
          {text ?? name}
          {text && " "}
          <span className="sr-only">{text ? `for ${name}, ` : ", "}open stats</span>
        </span>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-page/70" />
        <Dialog.Content
          onCloseAutoFocus={(e) => closedByNavigation.current && e.preventDefault()}
          className="fixed inset-x-0 bottom-0 z-50 max-h-[85vh] overflow-y-auto rounded-t-2xl border-x border-t border-border bg-surface p-4 pb-[max(1rem,env(safe-area-inset-bottom))] outline-hidden md:inset-y-0 md:left-auto md:right-0 md:max-h-none md:w-[28rem] md:rounded-none md:border-y-0 md:border-r-0 md:border-l"
        >
          <div className="flex items-start justify-between gap-2">
            <Dialog.Title className="text-heading font-semibold">{name}</Dialog.Title>
            <Dialog.Close aria-label="Close" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-text">
              <X size={20} aria-hidden />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">This season's weekly game log and league points.</Dialog.Description>
          <PlayerSheetBody
            gsisId={gsisId}
            position={position}
            season={season}
            onNavigate={() => {
              closedByNavigation.current = true;
              setOpen(false);
            }}
          />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
