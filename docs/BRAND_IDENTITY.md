# Ask Mahmoud — unified professional identity

## Canonical identity
- Public brand: **اسأل محمود**
- Professional name: **محمود خيرت رجب**
- Professional title: **محامٍ ومستشار قانوني في مصر**
- Descriptor: **خدمات قانونية للأفراد والشركات**
- Service area: **متابعة القضايا في القاهرة والجيزة | استشارات أونلاين في جميع محافظات مصر**
- Spoken sign-off: **خليك فاكر دايما ... اسأل محمود**

## Visual system
- Primary: deep navy `#0C1C30`
- Accent: muted gold `#BE974C`
- Text: white `#FFFFFF`
- Editorial style: contemporary, restrained, credible, documentary/editorial photography.
- Every image must depict the concrete legal issue, evidence, action, or document described by the actual post. Generic gavels, scales, courthouse exteriors, handshakes, and anonymous office stock images are not acceptable substitutes.
- No generated text, fake seals, signatures, court stamps, logos, or invented legal documents. Add brand typography in code after image generation.
- Use the same brand lockup across Blogger, Facebook, LinkedIn, Reels, and YouTube Shorts. Platform-specific formatting may change; the professional identity must not.

## Copy rules
- Write in clear Egyptian Arabic for public educational content; use precise formal Arabic for legal terminology when needed.
- Explain practical next steps without promising case outcomes.
- Keep the legal scope grounded in verified source material.
- Do not present the practice as companies-only: the service descriptor explicitly covers individuals and companies.
- Keep the name, title, service scope, geographic scope, logo, palette, and slogan consistent across profile bios, post footers, video end cards, and website metadata.

## Implementation
`src/brand_identity.py` is the single source of truth for identity text, colors, slogan, and post-grounded image prompt construction. Image and video modules import these values instead of maintaining separate hard-coded brand descriptions.
