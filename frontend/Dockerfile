FROM node:22-slim AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

FROM node:22-slim
WORKDIR /app
RUN corepack enable
COPY --from=build /app/dist ./dist
EXPOSE 4173
CMD ["pnpm", "dlx", "serve", "-s", "dist", "-l", "4173"]
