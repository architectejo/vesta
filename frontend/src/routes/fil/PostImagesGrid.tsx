import { useState } from "react";
import { downloadPostImage, type Post } from "../../api/social";
import { AuthenticatedImage } from "../../design-system";
import { ImageViewerModal, type ViewerImage } from "./ImageViewerModal";

/** Une image publique (adresse absolue) s'affiche directement ; une image
 * « Club » n'est jamais servie par une adresse publique (point de sécurité
 * critique) : elle passe par la vue de téléchargement authentifiée. */
function PostImage({ image, alt, className, onClick }: { image: Post["images"][number]; alt: string; className: string; onClick: () => void }) {
  if (image.url && image.url.startsWith("http")) {
    return <img src={image.url} alt={alt} loading="lazy" onClick={onClick} className={className} />;
  }
  return (
    <AuthenticatedImage
      cacheKey={image.id}
      download={() => downloadPostImage(image.id)}
      alt={alt}
      onClick={onClick}
      className={className}
    />
  );
}

const GRID_CLASS: Record<number, string[]> = {
  1: ["col-span-2 row-span-2"],
  2: ["col-span-1 row-span-2", "col-span-1 row-span-2"],
  3: ["col-span-1 row-span-2", "col-span-1 row-span-1", "col-span-1 row-span-1"],
  4: ["col-span-1 row-span-1", "col-span-1 row-span-1", "col-span-1 row-span-1", "col-span-1 row-span-1"],
};

export function PostImagesGrid({ post }: { post: Post }) {
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  if (post.images.length === 0) return null;

  const count = Math.min(post.images.length, 4);
  const cellClasses = GRID_CLASS[count] ?? GRID_CLASS[4]!;

  const viewerImages: ViewerImage[] = post.images.map((image, i) => ({
    id: image.id,
    url: image.url && image.url.startsWith("http") ? image.url : null,
    download: image.url && image.url.startsWith("http") ? undefined : () => downloadPostImage(image.id),
    alt: `Image ${i + 1} sur ${post.images.length} de la publication de ${post.author.first_name} ${post.author.last_name}`,
  }));

  return (
    <>
      <div
        className={[
          "grid gap-1 overflow-hidden rounded-lg",
          count === 1 ? "grid-cols-2" : "grid-cols-2 grid-rows-2",
        ].join(" ")}
      >
        {post.images.slice(0, 4).map((image, i) => (
          <PostImage
            key={image.id}
            image={image}
            alt={`Image ${i + 1} sur ${post.images.length} de la publication de ${post.author.first_name} ${post.author.last_name}`}
            onClick={() => setViewerIndex(i)}
            className={[
              cellClasses[i] ?? "",
              count === 1 ? "max-h-[360px] w-full object-cover" : "h-full w-full object-cover",
              "cursor-pointer bg-skeleton",
            ].join(" ")}
          />
        ))}
      </div>
      {viewerIndex !== null ? (
        <ImageViewerModal images={viewerImages} startIndex={viewerIndex} onClose={() => setViewerIndex(null)} />
      ) : null}
    </>
  );
}
