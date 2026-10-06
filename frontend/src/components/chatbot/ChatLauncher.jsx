import { useState } from "react";
import { Sparkles, X } from "lucide-react";
import ChatPanel from "./ChatPanel";

export default function ChatLauncher() {
  const [open, setOpen] = useState(false);
  return (
    <>
      {open && <ChatPanel onClose={() => setOpen(false)} />}
      <button className="chat-fab" onClick={() => setOpen((v) => !v)} aria-label="AI Assistant">
        {open ? <X size={20} /> : <Sparkles size={20} />}
      </button>
    </>
  );
}
