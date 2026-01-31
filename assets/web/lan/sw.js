self.addEventListener("push", (event) => {
  let payload = {};
  if (event.data){
    try {
      payload = event.data.json();
    } catch (err){
      try {
        payload = { body: event.data.text() };
      } catch (parseErr){
        payload = {};
      }
    }
  }
  const title = payload.title || "InitTracker LAN";
  const body = payload.body || "You have a new alert.";
  const url = payload.url || "/";
  const options = {
    body,
    data: { url },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification && event.notification.data && event.notification.data.url) ? event.notification.data.url : "/";
  event.waitUntil((async () => {
    const clientList = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of clientList){
      client.postMessage({ type: "deep-link", url });
      if ("focus" in client){
        await client.focus();
        return;
      }
    }
    if (clients.openWindow){
      await clients.openWindow(url);
    }
  })());
});
