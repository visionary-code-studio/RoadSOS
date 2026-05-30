// ═══════════════════════════════════════════════════════════════
//  RoadSOS+ Firebase Cloud Messaging Service Worker
//  Handles background push notifications
// ═══════════════════════════════════════════════════════════════

importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js');

// Firebase config — fill in your project values
const firebaseConfig = {
  apiKey: "AIzaSyC2bAAWI653e2bK8DrWVaqmg7jMU-9Uhfk",
  authDomain: "roadsos-1e38d.firebaseapp.com",
  projectId: "roadsos-1e38d",
  storageBucket: "roadsos-1e38d.firebasestorage.app",
  messagingSenderId: "676701067701",
  appId: "1:676701067701:web:e08885396b0c836a6d61fc"
};

firebase.initializeApp(firebaseConfig);

const messaging = firebase.messaging();

// Handle background messages
messaging.onBackgroundMessage(function (payload) {
  console.log('[RoadSOS+ SW] Received background message:', payload);

  const notificationTitle = payload.notification?.title || '🚨 RoadSOS+ Alert';
  const notificationOptions = {
    body: payload.notification?.body || 'Emergency alert received.',
    icon: '/favicon.ico',
    badge: '/favicon.ico',
    tag: 'roadsos-notification',
    renotify: true,
    requireInteraction: true,
    data: payload.data || {},
    actions: [
      { action: 'view', title: '🗺 View Location' },
      { action: 'dismiss', title: 'Dismiss' }
    ]
  };

  self.registration.showNotification(notificationTitle, notificationOptions);
});

// Handle notification click
self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  if (event.action === 'view') {
    event.waitUntil(clients.openWindow('/'));
  } else {
    event.waitUntil(clients.openWindow('/'));
  }
});
