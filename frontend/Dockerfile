FROM nginx:alpine

COPY index.html /usr/share/nginx/html/index.html

# Créer les dossiers nécessaires et donner les droits complets à l'utilisateur nginx
RUN mkdir -p /var/cache/nginx /var/run/nginx /var/log/nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx /var/run/nginx /var/log/nginx /usr/share/nginx/html

# Rediriger proprement le pid vers un sous-dossier où l'utilisateur nginx a les droits
RUN echo "pid /var/run/nginx/nginx.pid;" > /etc/nginx/conf.d/pid.conf

USER nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]