import { useEffect, useState } from "react";
import clsx from "clsx";

export default function Toast({ message, type = "success", onClose, duration = 3000 }) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      setTimeout(onClose, 300);
    }, duration);
    return () => clearTimeout(timer);
  }, [duration, onClose]);

  return (
    <div
      className={clsx(
        "px-4 py-2.5 rounded-lg text-sm font-medium border shadow-lg",
        "transition-all duration-300",
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2",
        {
          "bg-zinc-900 border-zinc-700 text-zinc-200": type === "success",
          "bg-zinc-900 border-red-500/40 text-red-400": type === "error",
          "bg-zinc-900 border-yellow-500/40 text-yellow-400": type === "warning",
          "bg-zinc-900 border-zinc-700 text-zinc-300": type === "info",
        }
      )}
    >
      {message}
    </div>
  );
}

import { useState as useStateHook, useCallback } from "react";

export function useToast() {
  const [toasts, setToasts] = useStateHook([]);

  const showToast = useCallback((message, type = "success") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const ToastContainer = () => (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <Toast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          onClose={() => removeToast(toast.id)}
        />
      ))}
    </div>
  );

  return { showToast, ToastContainer };
}
