import { ICSelector } from "./ic-selector";

export default function DevicesPage() {
  return (
    <main className="devicesPage">
      <ICSelector usage="lookup" />
    </main>
  );
}
