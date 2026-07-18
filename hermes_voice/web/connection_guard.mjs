export class ConnectionGuard {
  constructor() {
    this._generation = 0;
    this._current = null;
  }

  activate(socket) {
    if (!socket) throw new TypeError("socket is required");
    const connection = Object.freeze({
      socket,
      generation: ++this._generation,
    });
    this._current = connection;
    return connection;
  }

  isCurrent(connection) {
    return (
      connection !== null
      && connection === this._current
      && connection.generation === this._generation
    );
  }

  invalidate(connection) {
    if (!this.isCurrent(connection)) return false;
    this._generation += 1;
    this._current = null;
    return true;
  }

  get current() {
    return this._current;
  }
}

export function guardConnectionCallback(guard, connection, callback) {
  return (...args) => {
    if (!guard.isCurrent(connection)) return undefined;
    return callback(...args);
  };
}
