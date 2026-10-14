FROM nginx:alpine

COPY index.html /usr/share/nginx/html/index.html

# Création des dossiers et attribution des droits à l'utilisateur nginx
RUN mkdir -p /var/cache/nginx /var/run /var/log/nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx /usr/share/nginx/html

# Correction du chemin exact du PID pour l'image alpine actuelle
RUN sed -i 's#/run/nginx.pid#/tmp/nginx.pid#' /etc/nginx/nginx.conf

USER nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]