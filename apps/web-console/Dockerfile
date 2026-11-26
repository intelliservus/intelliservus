FROM node:22-alpine AS build

RUN corepack enable

WORKDIR /repo
COPY . .
RUN pnpm install --frozen-lockfile
RUN pnpm --filter web-console build

FROM nginx:1.29-alpine

COPY apps/web-console/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web-console/dist /usr/share/nginx/html

EXPOSE 80
