# Multi-stage production build for the Next.js frontend (§21.1).
# Uses Next.js standalone output so the runtime image ships only the compiled
# server plus its traced node_modules — no full dev dependency tree.
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
RUN groupadd --gid 1000 nodeapp \
    && useradd --uid 1000 --gid nodeapp --create-home nodeapp
COPY --from=build --chown=nodeapp:nodeapp /app/public ./public
COPY --from=build --chown=nodeapp:nodeapp /app/.next/standalone ./
COPY --from=build --chown=nodeapp:nodeapp /app/.next/static ./.next/static
USER nodeapp
EXPOSE 3000
CMD ["node", "server.js"]
