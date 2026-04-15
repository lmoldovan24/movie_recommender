import { useState } from "react";
import clsx from "clsx";

export default function StarRating({ rating = 0, onChange, readonly = false, size = "md" }) {
  const [hovered, setHovered] = useState(null);

  const stars = [1, 2, 3, 4, 5];
  const active = hovered ?? rating;

  const sizeClass = {
    sm: "text-lg",
    md: "text-2xl",
    lg: "text-3xl",
  }[size];

  return (
    <div className="flex items-center gap-0.5">
      {stars.map((star) => (
        <span key={star} className="relative inline-flex">
          {/* Half star — stânga */}
          <span
            className={clsx(
              "absolute left-0 top-0 w-1/2 h-full z-10",
              !readonly && "cursor-pointer"
            )}
            onMouseEnter={() => !readonly && setHovered(star - 0.5)}
            onMouseLeave={() => !readonly && setHovered(null)}
            onClick={() => !readonly && onChange?.(star - 0.5)}
          />
          {/* Full star — dreapta */}
          <span
            className={clsx(
              "absolute right-0 top-0 w-1/2 h-full z-10",
              !readonly && "cursor-pointer"
            )}
            onMouseEnter={() => !readonly && setHovered(star)}
            onMouseLeave={() => !readonly && setHovered(null)}
            onClick={() => !readonly && onChange?.(star)}
          />
          <span
            className={clsx(sizeClass, "select-none transition-colors duration-100", {
              "text-yellow-400": active >= star,
              "text-yellow-200": active >= star - 0.5 && active < star,
              "text-zinc-700": active < star - 0.5,
            })}
            aria-label={`${star} stele`}
          >
            ★
          </span>
        </span>
      ))}
      {rating > 0 && (
        <span className="ml-1 text-sm text-zinc-500">{rating.toFixed(1)}</span>
      )}
    </div>
  );
}
