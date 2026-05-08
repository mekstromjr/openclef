// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// https://astro.build/config
export default defineConfig({
  // Eventual public URL: openclef.meklab.net (then openclef.org).
  // Update `site` when DNS lands so sitemap + OG URLs resolve correctly.
  site: "https://openclef.meklab.net",

  integrations: [
    starlight({
      title: "OpenClef",
      description:
        "Self-hosted sheet music library for families and musicians. New tools for a timeless medium.",
      customCss: ["./src/styles/brand.css"],

      social: [
        {
          icon: "gitlab",
          label: "GitLab",
          href: "https://gitlab.meklab.net/meklab/openclef",
        },
      ],

      sidebar: [
        {
          label: "Brand",
          items: [
            { label: "Overview", slug: "brand" },
            { label: "Logo & iconography", slug: "brand/logo" },
            { label: "Typography", slug: "brand/typography" },
            { label: "Color", slug: "brand/color" },
            { label: "Imagery", slug: "brand/imagery" },
            { label: "Voice & tone", slug: "brand/voice" },
            { label: "Naming", slug: "brand/naming" },
            { label: "Press kit", slug: "brand/press-kit" },
          ],
        },
        {
          label: "Guides",
          items: [{ autogenerate: { directory: "guides" } }],
        },
        {
          label: "Reference",
          items: [{ autogenerate: { directory: "reference" } }],
        },
      ],
    }),
  ],
});
