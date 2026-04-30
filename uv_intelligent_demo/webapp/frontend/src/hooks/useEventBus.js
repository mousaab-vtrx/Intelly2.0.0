import { useEffect, useRef, useCallback } from "react";

// Event-driven architecture for cross-component communication
const eventBus = {
  events: {},
  subscribe(eventName, callback) {
    if (!this.events[eventName]) {
      this.events[eventName] = [];
    }
    this.events[eventName].push(callback);
    return () => {
      this.events[eventName] = this.events[eventName].filter((cb) => cb !== callback);
    };
  },
  publish(eventName, data) {
    if (this.events[eventName]) {
      this.events[eventName].forEach((callback) => callback(data));
    }
  },
  clear() {
    this.events = {};
  },
};

export function useEventBus() {
  return eventBus;
}

export function useEventSubscribe(eventName, callback, deps = []) {
  const bus = useEventBus();
  useEffect(() => {
    const unsubscribe = bus.subscribe(eventName, callback);
    return unsubscribe;
  }, [eventName, ...deps]);
}

export function useEventPublish() {
  const bus = useEventBus();
  return useCallback((eventName, data) => {
    bus.publish(eventName, data);
  }, []);
}
