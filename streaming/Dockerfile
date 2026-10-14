FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN mkdir -p /var/cache/nginx /var/run /var/log/nginx && \
    chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx

RUN sed -i 's#/var/run/nginx.pid#/tmp/nginx.pid#' /etc/nginx/nginx.conf

USER nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]