FROM node:20.18-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM deps AS builder

WORKDIR /app
COPY . .
RUN npm run build

FROM deps AS test

WORKDIR /app
COPY . .
USER node
CMD ["npm", "test", "--", "--run"]

FROM node:20.18-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --system --gid 10001 nextjs \
    && adduser --system --uid 10001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static

USER 10001:10001
EXPOSE 3000

CMD ["node", "server.js"]
