FROM nginx:alpine

COPY index.html /usr/share/nginx/html/index.html

# Créer les dossiers nécessaires et donner les droits à l'utilisateur nginx
RUN mkdir -p /var/cache/nginx /var/run /var/log/nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx /usr/share/nginx/html

# Rediriger le fichier pid vers /tmp/nginx.pid dans le fichier de configuration global
RUN sed -i 's#/var/run/nginx.pid#/tmp/nginx.pid#' /etc/nginx/nginx.conf

USER nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]